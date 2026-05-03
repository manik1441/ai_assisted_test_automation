"""DB Agent — SQL validation scenario generation.

Responsibilities:
- Receive test intent (from PipelineContext).
- Call LLM with db_agent.md system prompt.
- Parse and validate the scenario JSON.
- Write test_scenarios back to PipelineContext.
"""

from __future__ import annotations

import logging

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.exceptions import AgentError

logger = logging.getLogger(__name__)


class DBAgent(BaseAgent):
    """Generates SQL data validation scenarios from test intent."""

    @property
    def agent_name(self) -> str:
        return "db_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Generate DB test scenarios and enrich the context.

        Sets:
            context.test_scenarios — list of scenario dicts
        """
        if context.test_type != "db":
            self._logger.debug(
                "DBAgent skipped: test_type=%s", context.test_type
            )
            return context

        self._logger.info(
            "Generating DB scenarios for intent: %s", context.intent
        )

        prompt = self._build_prompt(context)

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise AgentError(
                f"DBAgent LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        scenarios: list[dict] = result.get("scenarios", [])
        if not scenarios:
            context.add_error("DBAgent: LLM returned no scenarios.")
            self._logger.warning("DBAgent returned empty scenarios.")

        context.test_scenarios = scenarios

        self._post(
            context=context,
            message_type="db_scenarios",
            payload={"scenario_count": len(scenarios)},
        )

        self._logger.info("DBAgent generated %d scenario(s).", len(scenarios))
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, context: PipelineContext) -> str:
        lines = [
            f"Test Intent: {context.intent}",
            f"Raw Prompt: {context.raw_prompt}",
        ]

        if context.tasks:
            lines.append("\nTasks to cover:")
            for task in context.tasks:
                lines.append(f"  - {task.description}")

        return "\n".join(lines)
