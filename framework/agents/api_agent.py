"""API Agent — REST/GraphQL test scenario generation.

Responsibilities:
- Receive test intent (from PipelineContext).
- Call LLM with api_agent.md system prompt.
- Parse and validate the scenario JSON.
- Write test_scenarios back to PipelineContext.
"""

from __future__ import annotations

import logging

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.exceptions import AgentError

logger = logging.getLogger(__name__)


class APIAgent(BaseAgent):
    """Generates API test scenarios (requests-based) from test intent."""

    @property
    def agent_name(self) -> str:
        return "api_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Generate API test scenarios and enrich the context.

        Sets:
            context.test_scenarios — list of scenario dicts
        """
        if context.test_type != "api":
            self._logger.debug(
                "APIAgent skipped: test_type=%s", context.test_type
            )
            return context

        self._logger.info(
            "Generating API scenarios for intent: %s", context.intent
        )

        prompt = self._build_prompt(context)

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise AgentError(
                f"APIAgent LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        scenarios: list[dict] = result.get("scenarios", [])
        if not scenarios:
            context.add_error("APIAgent: LLM returned no scenarios.")
            self._logger.warning("APIAgent returned empty scenarios.")

        # Attach base_url_placeholder for TestScriptAgent
        base_url_placeholder = result.get("base_url_placeholder", "BASE_URL")
        for scenario in scenarios:
            scenario["base_url_placeholder"] = base_url_placeholder

        context.test_scenarios = scenarios

        self._post(
            context=context,
            message_type="api_scenarios",
            payload={"scenario_count": len(scenarios)},
        )

        self._logger.info("APIAgent generated %d scenario(s).", len(scenarios))
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
