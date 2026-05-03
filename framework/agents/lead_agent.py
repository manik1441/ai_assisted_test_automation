"""Lead Agent — intent detection and test type classification.

Responsibilities:
- Read the raw user prompt.
- Call the LLM with the lead_agent.md system prompt.
- Parse the response as JSON.
- Write test_type and intent back to PipelineContext.
- Post a "classification" message to the bus.
"""

from __future__ import annotations

import logging

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.exceptions import ClassificationError

logger = logging.getLogger(__name__)

VALID_TEST_TYPES = {"ui", "api", "db"}


class LeadAgent(BaseAgent):
    """Classifies user intent and determines test type."""

    @property
    def agent_name(self) -> str:
        return "lead_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Classify the user prompt and enrich the context.

        Sets:
            context.test_type — "ui" | "api" | "db"
            context.intent    — one-sentence test intent
        """
        self._logger.info(
            "Classifying prompt",
            extra={"correlation_id": context.correlation_id},
        )

        prompt = self._build_prompt(context)

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise ClassificationError(
                f"LeadAgent LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        test_type = result.get("test_type", "").lower()
        if test_type not in VALID_TEST_TYPES:
            raise ClassificationError(
                f"LLM returned invalid test_type: '{test_type}'",
                details={"valid_types": list(VALID_TEST_TYPES), "raw": result},
            )

        context.test_type = test_type
        context.intent = result.get("intent", context.raw_prompt)
        # source may override if the LLM detected hybrid/jira
        if llm_source := result.get("source"):
            context.source = llm_source

        self._post(
            context=context,
            message_type="classification",
            payload={
                "test_type": context.test_type,
                "intent": context.intent,
                "source": context.source,
            },
        )

        # Persist to vector store for few-shot reuse in future runs
        try:
            self._vector_store.store_prompt(
                prompt_id=context.correlation_id,
                prompt=context.raw_prompt,
                test_type=context.test_type,
                metadata={"intent": context.intent},
            )
        except Exception as exc:
            # Non-fatal — log and continue
            context.add_error(f"VectorStore: failed to store prompt — {exc}")
            self._logger.warning("Failed to store prompt in vector store: %s", exc)

        self._logger.info(
            "Classification complete: test_type=%s", context.test_type
        )
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, context: PipelineContext) -> str:
        """Build the user-turn prompt, optionally including few-shot neighbours."""
        lines = [f"User Prompt: {context.raw_prompt}"]

        # Retrieve similar past prompts from vector store for context
        try:
            neighbours = self._vector_store.find_similar_prompts(
                context.raw_prompt, n_results=2
            )
            if neighbours:
                lines.append("\nSimilar past prompts for reference:")
                for n in neighbours:
                    lines.append(
                        f"  - \"{n.entry.content}\" → {n.entry.metadata.get('test_type')}"
                    )
        except Exception:
            pass  # Vector store lookup is best-effort

        return "\n".join(lines)
