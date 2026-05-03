"""Self-Healing Agent — analyzes failures and suggests fixes.

Responsibilities:
- Detect failed tests from ExecutionResult.
- Read pytest_report.json for failure details (stack traces, logs).
- Match failures back to generated scripts.
- Call LLM with self_healing_agent.md system prompt for analysis and fixes.
- Store results in PipelineContext.self_healing_results.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from framework.core.base_agent import BaseAgent, PipelineContext

logger = logging.getLogger(__name__)


class SelfHealingAgent(BaseAgent):
    """Analyzes test failures and provides healed code suggestions."""

    @property
    def agent_name(self) -> str:
        return "self_healing_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Analyze failures and provide healing suggestions."""
        if not context.execution_result or (context.execution_result.failed == 0 and context.execution_result.errors == 0):
            self._logger.info("No failures detected — skipping self-healing.")
            return context

        self._logger.info("Analyzing failures for self-healing...")

        # Load pytest JSON report to get detailed failure info
        report_path = Path(self._config.reporting.report_dir) / "pytest_report.json"
        if not report_path.exists():
            self._logger.warning("pytest_report.json not found — skipping.")
            return context

        try:
            report_data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._logger.error("Failed to read pytest report: %s", exc)
            return context

        results = []
        # Process failures in tests
        for test_result in report_data.get("tests", []):
            if test_result.get("outcome") == "failed":
                self._analyze_failure(test_result, context, results)

        # Process failures in collectors (SyntaxErrors, ImportErrors, etc.)
        for collector in report_data.get("collectors", []):
            if collector.get("outcome") == "failed":
                self._analyze_failure(collector, context, results)

        context.self_healing_results = results

        self._post(
            context=context,
            message_type="healing_complete",
            payload={
                "failure_count": len(results),
                "healed_count": sum(1 for r in results if r.get("healed_content")),
            },
        )
        return context

    def _analyze_failure(self, item: dict, context: PipelineContext, results: list):
        """Analyze a single failure item (test or collector)."""
        nodeid = item.get("nodeid", "unknown")
        
        # Extract error message (differs between test and collector)
        error_message = item.get("longrepr", "")
        if not error_message:
            error_message = item.get("call", {}).get("longrepr", "No error trace found.")

        # Match back to script
        script_filename = nodeid.split("::")[0].split("/")[-1]
        if not script_filename and nodeid:
             script_filename = nodeid
             
        original_content = ""
        for script in context.generated_scripts:
            if script.filename == script_filename:
                original_content = script.content
                break
        
        if not original_content:
            try:
                # Fallback to searching disk
                for p in Path(self._config.execution.output_dir).rglob(script_filename):
                    original_content = p.read_text(encoding="utf-8")
                    break
            except: pass

        # Call LLM for healing
        healing_prompt = self._build_healing_prompt(
            intent=context.intent or "Unknown intent",
            script_content=original_content,
            error_message=error_message,
            logs=item.get("call", {}).get("stdout", "")
        )

        try:
            analysis_result = self._llm.generate_json(
                prompt=healing_prompt,
                system_prompt=self._system_prompt,
            )
            analysis_result["test_nodeid"] = nodeid
            analysis_result["filename"] = script_filename
            results.append(analysis_result)
        except Exception as exc:
            self._logger.error("LLM healing call failed for %s: %s", nodeid, exc)

    def _build_healing_prompt(self, intent: str, script_content: str, error_message: str, logs: str) -> str:
        return f"""
Analyze the following test failure and provide a fix.

Original Intent: {intent}

Original Script:
```python
{script_content}
```

Error Message / Stack Trace:
{error_message}

Captured Logs (stdout):
{logs}
"""
