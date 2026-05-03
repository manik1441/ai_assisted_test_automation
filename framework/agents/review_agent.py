"""Review Agent — quality gate for generated test scripts.

Responsibilities:
- Receive generated_scripts from PipelineContext.
- Build a review prompt that includes each script's content.
- Call LLM with review_agent.md system prompt.
- Parse the review results list.
- Write review_results back to PipelineContext.
- Flag scripts that failed review so the Orchestrator can decide next steps.
"""

from __future__ import annotations

import logging

from framework.core.base_agent import BaseAgent, PipelineContext, ReviewResult
from framework.core.exceptions import ReviewError

logger = logging.getLogger(__name__)


class ReviewAgent(BaseAgent):
    """Reviews generated test scripts for quality and best-practice compliance."""

    @property
    def agent_name(self) -> str:
        return "review_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Review all generated scripts and enrich the context.

        Sets:
            context.review_results — list of ReviewResult objects
        """
        if not context.generated_scripts:
            context.add_error(
                "ReviewAgent: no generated scripts to review."
            )
            self._logger.warning("No scripts to review — skipping.")
            return context

        self._logger.info(
            "Reviewing %d script(s).", len(context.generated_scripts)
        )

        prompt = self._build_prompt(context)

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise ReviewError(
                f"ReviewAgent LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        raw_results: list[dict] = result.get("results", [])
        if not raw_results:
            context.add_error("ReviewAgent: LLM returned no review results.")
            self._logger.warning("ReviewAgent returned empty results.")
            return context

        review_results: list[ReviewResult] = []
        failed_count = 0

        for raw in raw_results:
            review = ReviewResult(
                script_id=raw.get("script_id", "unknown"),
                passed=raw.get("passed", True),
                issues=raw.get("issues", []),
                suggestions=raw.get("suggestions", []),
            )
            review_results.append(review)

            if not review.passed:
                failed_count += 1
                self._logger.warning(
                    "Script '%s' failed review: %s",
                    review.script_id,
                    review.issues,
                )

        context.review_results = review_results

        self._post(
            context=context,
            message_type="review_complete",
            payload={
                "total_reviewed": len(review_results),
                "passed": len(review_results) - failed_count,
                "failed": failed_count,
            },
        )

        self._logger.info(
            "Review complete: %d passed, %d failed.",
            len(review_results) - failed_count,
            failed_count,
        )
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, context: PipelineContext) -> str:
        """Build a review prompt containing all scripts with their IDs."""
        sections = ["Review the following test scripts:\n"]
        for script in context.generated_scripts:
            sections.append(
                f"--- Script ID: {script.script_id} | File: {script.filename} ---\n"
                f"{script.content}\n"
            )
        return "\n".join(sections)
