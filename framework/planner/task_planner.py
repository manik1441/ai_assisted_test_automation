"""Task Planner — converts classified intent into an ordered task list.

Responsibilities:
- Receive test_type and intent from PipelineContext (set by LeadAgent).
- Call LLM to decompose the intent into discrete, atomic tasks.
- Write tasks list back to PipelineContext.

A Task represents one testable unit of work (e.g. one scenario or one
endpoint). The specialist agents (UI/API/DB) use tasks to scope their
scenario generation.
"""

from __future__ import annotations

import logging
import uuid

from framework.core.base_agent import BaseAgent, PipelineContext, Task
from framework.core.exceptions import AgentError

logger = logging.getLogger(__name__)

# System prompt is inlined here since task planning is generic and
# does not warrant a separate .md file (it operates on LeadAgent output).
_TASK_PLANNER_SYSTEM_PROMPT = """
You are the Task Planner of the Agentic TestGen Framework (ATF).

Given a test intent and test type (ui, api, or db), decompose the intent
into discrete, atomic test tasks. Each task represents one specific scenario
or test case that should be generated.

Return a JSON object in exactly this format:
{
  "tasks": [
    {
      "task_id": "<unique id>",
      "description": "<one sentence describing this specific test case>",
      "test_type": "<ui | api | db>",
      "priority": <1 for critical, 2 for high, 3 for medium>
    }
  ]
}

Rules:
- Keep each task description concise and specific.
- Cover both happy path and negative/edge cases.
- Maximum 8 tasks per intent. Prioritise coverage over quantity.
- All tasks must share the same test_type as the input.
""".strip()


class TaskPlanner(BaseAgent):
    """Decomposes intent into an ordered list of test tasks."""

    @property
    def agent_name(self) -> str:
        return "task_planner"

    def _load_system_prompt(self) -> str:
        """TaskPlanner uses an inlined system prompt — no .md file needed."""
        return _TASK_PLANNER_SYSTEM_PROMPT

    def run(self, context: PipelineContext) -> PipelineContext:
        """Decompose intent into tasks and enrich the context.

        Sets:
            context.tasks — ordered list of Task objects
        """
        if not context.intent:
            context.add_error("TaskPlanner: intent is empty, cannot plan tasks.")
            self._logger.warning("Skipping task planning — no intent available.")
            return context

        self._logger.info(
            "Planning tasks for intent: %s (type=%s)",
            context.intent,
            context.test_type,
        )

        prompt = (
            f"Test Type: {context.test_type}\n"
            f"Intent: {context.intent}\n"
            f"Raw Prompt: {context.raw_prompt}"
        )

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise AgentError(
                f"TaskPlanner LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        raw_tasks: list[dict] = result.get("tasks", [])
        if not raw_tasks:
            context.add_error("TaskPlanner: LLM returned no tasks.")
            self._logger.warning("TaskPlanner returned empty tasks list.")
            return context

        tasks: list[Task] = []
        for raw in raw_tasks:
            tasks.append(
                Task(
                    task_id=raw.get("task_id") or str(uuid.uuid4()),
                    description=raw.get("description", ""),
                    test_type=raw.get("test_type", context.test_type or "ui"),
                    priority=raw.get("priority", 2),
                )
            )

        # Sort by priority (1 = highest)
        tasks.sort(key=lambda t: t.priority)
        context.tasks = tasks

        self._post(
            context=context,
            message_type="tasks_planned",
            payload={
                "task_count": len(tasks),
                "tasks": [t.description for t in tasks],
            },
        )

        self._logger.info("TaskPlanner created %d task(s).", len(tasks))
        return context
