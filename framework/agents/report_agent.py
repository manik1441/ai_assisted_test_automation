"""Report Agent — processes pytest execution results and produces summaries.

Responsibilities:
- Read execution_result from PipelineContext.
- Call LLM with report_agent.md system prompt if failures need analysis.
- Write report_path to PipelineContext.
- Print/return a structured execution summary.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.exceptions import AgentError

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """Processes execution results and generates an Allure-linked summary."""

    @property
    def agent_name(self) -> str:
        return "report_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Generate the execution report summary.

        Sets:
            context.report_path — path to Allure results directory
        """
        report_dir = Path(self._config.reporting.report_dir)
        allure_results_dir = report_dir / "allure-results"
        report_dir.mkdir(parents=True, exist_ok=True)

        context.report_path = str(allure_results_dir)

        summary = self._build_summary(context)

        # Write JSON summary alongside Allure results
        summary_path = report_dir / "atf_summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

        self._post(
            context=context,
            message_type="report_ready",
            payload={"report_path": str(allure_results_dir), "summary": summary},
        )

        self._logger.info(
            "Report written to %s", str(report_dir)
        )
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_summary(self, context: PipelineContext) -> dict:
        """Build the summary dict from execution_result and review_results."""
        exec_result = context.execution_result

        if exec_result:
            pass_rate = (
                round(exec_result.passed / exec_result.total * 100, 1)
                if exec_result.total > 0
                else 0.0
            )
            summary = {
                "correlation_id": context.correlation_id,
                "test_type": context.test_type,
                "intent": context.intent,
                "execution": {
                    "total": exec_result.total,
                    "passed": exec_result.passed,
                    "failed": exec_result.failed,
                    "errors": exec_result.errors,
                    "duration_seconds": exec_result.duration_seconds,
                    "pass_rate_percent": pass_rate,
                },
                "scripts_generated": len(context.generated_scripts),
                "scripts_reviewed": len(context.review_results),
                "review_failures": [
                    {"script_id": r.script_id, "issues": r.issues}
                    for r in context.review_results
                    if not r.passed
                ],
                "pipeline_errors": context.pipeline_errors,
                "report_path": context.report_path,
                "self_healing": {
                    "analyzed_failures": len(context.self_healing_results),
                    "healed_scripts": [
                        r.get("filename") for r in context.self_healing_results 
                        if r.get("healed_content")
                    ],
                    "details": [
                        {
                            "test": r.get("test_nodeid"),
                            "cause": r.get("analysis", {}).get("root_cause")
                        } for r in context.self_healing_results
                    ]
                },
                "next_actions": self._next_actions(context),
            }
        else:
            # Execution not run — report generation only
            summary = {
                "correlation_id": context.correlation_id,
                "test_type": context.test_type,
                "intent": context.intent,
                "scripts_generated": len(context.generated_scripts),
                "scripts_reviewed": len(context.review_results),
                "pipeline_errors": context.pipeline_errors,
                "report_path": context.report_path,
                "note": "Tests were generated but not executed in this run.",
                "next_actions": [
                    f"Run: pytest {self._config.execution.output_dir} "
                    f"--alluredir={context.report_path}",
                    f"View report: allure serve {context.report_path}",
                ],
            }

        return summary

    def _next_actions(self, context: PipelineContext) -> list[str]:
        actions = [
            f"View interactive report: allure serve {context.report_path}"
        ]
        if context.execution_result and context.execution_result.failed > 0:
            actions.insert(
                0,
                f"Investigate {context.execution_result.failed} failing test(s) "
                "in the Allure report.",
            )
        return actions
