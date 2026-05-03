"""Orchestrator — entry point and pipeline coordinator.

The Orchestrator:
  1. Creates all agent instances (single dependency injection point).
  2. Configures logging via LogAgent.
  3. Accepts a run request and creates a PipelineContext.
  4. Executes agents in the defined pipeline order.
  5. Optionally runs pytest and collects execution results.
  6. Returns the completed PipelineContext.

Usage:
    from framework.orchestrator.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    context = orchestrator.run("Test login with valid and invalid credentials")
"""

from __future__ import annotations

import subprocess
import time
import uuid
import logging
from pathlib import Path

from framework.core.base_agent import ExecutionResult, PipelineContext
from framework.core.config import Config, load_config
from framework.core.exceptions import ATFBaseException, ExecutionError
from framework.core.llm_provider import create_llm_provider
from framework.core.message_bus import MessageBus
from framework.core.vector_store import ATFVectorStore

from framework.agents.lead_agent import LeadAgent
from framework.agents.ui_agent import UIAgent
from framework.agents.api_agent import APIAgent
from framework.agents.db_agent import DBAgent
from framework.agents.test_script_agent import TestScriptAgent
from framework.agents.review_agent import ReviewAgent
from framework.agents.report_agent import ReportAgent
from framework.agents.log_agent import LogAgent, configure_logging
from framework.agents.cicd_agent import CICDAgent
from framework.agents.self_healing_agent import SelfHealingAgent
from framework.planner.task_planner import TaskPlanner

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the full ATF test generation and execution pipeline."""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or load_config()

        # Configure logging first so all subsequent logs are captured
        configure_logging(self._config.logging)

        # Shared infrastructure
        self._bus = MessageBus()
        self._llm = create_llm_provider(self._config)
        self._vector_store = ATFVectorStore(self._config.vector_store)

        # Agent instances — constructed once, reused across runs
        _agent_kwargs = dict(
            config=self._config,
            llm=self._llm,
            vector_store=self._vector_store,
            bus=self._bus,
        )

        self._lead_agent = LeadAgent(**_agent_kwargs)
        self._task_planner = TaskPlanner(**_agent_kwargs)
        self._ui_agent = UIAgent(**_agent_kwargs)
        self._api_agent = APIAgent(**_agent_kwargs)
        self._db_agent = DBAgent(**_agent_kwargs)
        self._test_script_agent = TestScriptAgent(**_agent_kwargs)
        self._review_agent = ReviewAgent(**_agent_kwargs)
        self._report_agent = ReportAgent(**_agent_kwargs)
        self._log_agent = LogAgent(**_agent_kwargs)
        self._self_healing_agent = SelfHealingAgent(**_agent_kwargs)
        self._cicd_agent = CICDAgent(**_agent_kwargs)

        logger.info("Orchestrator initialised with model: %s", self._config.llm.model)

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        *,
        jira_ticket_id: str | None = None,
        execute: bool = False,
        generate_cicd: bool = False,
        test_path: str | None = None,
    ) -> PipelineContext:
        """Execute the full test generation pipeline.

        Args:
            prompt:          Natural language test intent (required).
            jira_ticket_id:  If provided, enrich prompt from Jira ticket.
            execute:         If True, run pytest after generation.
            generate_cicd:   If True, generate CI/CD pipeline YAML.

        Returns:
            Completed PipelineContext with all agent outputs.
        """
        correlation_id = str(uuid.uuid4())
        source = "prompt"
        if jira_ticket_id:
            source = "jira"
            prompt = self._enrich_from_jira(prompt, jira_ticket_id)

        context = PipelineContext(
            correlation_id=correlation_id,
            raw_prompt=prompt,
            source=source,
            jira_ticket_id=jira_ticket_id,
        )

        logger.info(
            "Pipeline started | correlation_id=%s | source=%s",
            correlation_id, source,
        )

        try:
            context = self._run_pipeline(
                context, 
                execute=execute, 
                generate_cicd=generate_cicd,
                test_path=test_path
            )
        except ATFBaseException as exc:
            context.add_error(str(exc))
            logger.error("Pipeline error: %s", exc)
        finally:
            self._log_agent.run(context)

        return context

    # ──────────────────────────────────────────────────────────────────
    # Pipeline steps
    # ──────────────────────────────────────────────────────────────────

    def _run_pipeline(
        self,
        context: PipelineContext,
        *,
        execute: bool,
        generate_cicd: bool,
        test_path: str | None = None,
    ) -> PipelineContext:
        """Execute all pipeline stages in order."""

        # Stage 1: Classify intent
        context = self._lead_agent.run(context)

        # Stage 2: Decompose into tasks
        context = self._task_planner.run(context)

        # Stage 3: Specialist agent (route by test_type)
        context = self._route_specialist(context)

        # Stage 4: Generate test scripts
        context = self._test_script_agent.run(context)

        # Stage 5: Review scripts
        context = self._review_agent.run(context)

        # Stage 6: Execute tests (optional)
        if execute:
            context = self._run_pytest(context, test_path=test_path)

        # Stage 7: Self-healing (if enabled and there were failures or errors)
        if execute and self._config.execution.self_healing and context.execution_result and (context.execution_result.failed > 0 or context.execution_result.errors > 0):
            context = self._self_healing_agent.run(context)

        # Stage 8: Generate report
        context = self._report_agent.run(context)

        # Stage 9: Generate CI/CD config (optional)
        if generate_cicd:
            context = self._cicd_agent.run(context)

        return context

    def _route_specialist(self, context: PipelineContext) -> PipelineContext:
        """Route to the correct specialist agent based on test_type."""
        routing = {
            "ui": self._ui_agent,
            "api": self._api_agent,
            "db": self._db_agent,
        }
        agent = routing.get(context.test_type or "ui")
        if agent is None:
            raise ATFBaseException(
                f"No specialist agent for test_type: '{context.test_type}'"
            )
        return agent.run(context)

    def _run_pytest(self, context: PipelineContext, test_path: str | None = None) -> PipelineContext:
        """Run pytest on the generated test directory and capture results."""
        target = test_path if test_path else self._config.execution.output_dir
        test_dir = Path(target)
        report_dir = Path(self._config.reporting.report_dir) / "allure-results"
        report_dir.mkdir(parents=True, exist_ok=True)

        import sys
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_dir),
            f"--alluredir={report_dir}",
            "--tb=short",
            "-q",
            "--json-report",
            f"--json-report-file={self._config.reporting.report_dir}/pytest_report.json",
        ]

        logger.info("Running pytest: %s", " ".join(cmd))
        start = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            duration = time.monotonic() - start
        except subprocess.TimeoutExpired as exc:
            raise ExecutionError(
                "pytest execution timed out after 600 seconds."
            ) from exc
        except FileNotFoundError as exc:
            raise ExecutionError(
                "pytest not found — ensure it is installed in the active venv.",
                details={"cmd": cmd},
            ) from exc

        # Parse summary from pytest output
        context.execution_result = self._parse_pytest_output(
            proc.stdout + proc.stderr, duration
        )

        logger.info(
            "pytest completed in %.1fs | return_code=%s",
            duration, proc.returncode,
        )
        return context

    @staticmethod
    def _parse_pytest_output(output: str, duration: float) -> ExecutionResult:
        """Parse pytest -q output to extract pass/fail counts.

        Example last line: "3 passed, 1 failed in 4.52s"
        Falls back to zeros if parsing fails.
        """
        import re

        total = passed = failed = errors = 0

        pattern = re.compile(
            r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+error"
        )
        for match in pattern.finditer(output):
            if match.group(1):
                passed = int(match.group(1))
            if match.group(2):
                failed = int(match.group(2))
            if match.group(3):
                errors = int(match.group(3))

        total = passed + failed + errors

        return ExecutionResult(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            duration_seconds=round(duration, 2),
            report_dir="./reports/allure-results",
        )

    # ──────────────────────────────────────────────────────────────────
    # Jira integration (delegate to JiraConnector)
    # ──────────────────────────────────────────────────────────────────

    def _enrich_from_jira(self, prompt: str, ticket_id: str) -> str:
        """Fetch Jira ticket and prepend its description to the prompt."""
        if not self._config.jira.enabled:
            logger.warning(
                "Jira is disabled in config — using raw prompt only."
            )
            return prompt

        try:
            from framework.integrations.jira_connector import JiraConnector
            connector = JiraConnector(self._config.jira)
            ticket = connector.get_ticket(ticket_id)
            enriched = (
                f"Jira Ticket: {ticket_id}\n"
                f"Summary: {ticket.get('summary', '')}\n"
                f"Description: {ticket.get('description', '')}\n"
                f"Acceptance Criteria: {ticket.get('acceptance_criteria', '')}\n\n"
                f"Additional context: {prompt}"
            )
            logger.info("Prompt enriched from Jira ticket: %s", ticket_id)
            return enriched
        except Exception as exc:
            logger.warning(
                "Failed to fetch Jira ticket %s: %s — using raw prompt.",
                ticket_id, exc,
            )
            return prompt
