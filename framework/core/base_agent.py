"""Abstract BaseAgent — the contract every agent in ATF must fulfil.

Each concrete agent:
  1. Declares its agent_name property (must match the .md file in /agents/).
  2. Implements run(context) → enriches and returns the PipelineContext.
  3. Calls self.llm.generate() / self.llm.generate_json() for LLM work.
  4. Optionally calls self.vector_store and self.bus methods.

The BaseAgent loads the agent's system prompt from agents/<agent_name>.md
automatically at construction time.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from framework.core.config import Config
from framework.core.exceptions import AgentError
from framework.core.llm_provider import LLMProvider
from framework.core.message_bus import MessageBus, Message
from framework.core.vector_store import ATFVectorStore

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Shared pipeline data models (Pydantic)
# ──────────────────────────────────────────────────────────────────────────────

class Task(BaseModel):
    """A single unit of test work identified by the TaskPlanner."""

    task_id: str
    description: str
    test_type: str           # "ui" | "api" | "db"
    priority: int = 1        # 1 = highest
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedScript(BaseModel):
    """A pytest-compatible test script produced by TestScriptAgent."""

    script_id: str
    filename: str
    content: str             # Raw Python source code
    test_type: str
    task_id: str


class ReviewResult(BaseModel):
    """Outcome of the ReviewAgent for a single generated script."""

    script_id: str
    passed: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Outcome of running pytest."""

    total: int
    passed: int
    failed: int
    errors: int
    duration_seconds: float
    report_dir: str


class PipelineContext(BaseModel):
    """Mutable context object that flows through the entire pipeline.

    Each agent reads from it and writes its outputs back into it.
    The Orchestrator is the only entity that creates PipelineContext instances.
    """

    model_config = {"arbitrary_types_allowed": True}

    # Identity
    correlation_id: str

    # Input
    raw_prompt: str
    source: str = "prompt"          # "prompt" | "jira" | "hybrid"
    jira_ticket_id: str | None = None

    # Set by LeadAgent
    test_type: str | None = None    # "ui" | "api" | "db"
    intent: str | None = None

    # Set by TaskPlanner
    tasks: list[Task] = Field(default_factory=list)

    # Set by UI/API/DB Agent
    test_scenarios: list[dict[str, Any]] = Field(default_factory=list)

    # Set by TestScriptAgent
    generated_scripts: list[GeneratedScript] = Field(default_factory=list)

    # Set by ReviewAgent
    review_results: list[ReviewResult] = Field(default_factory=list)

    # Set by Orchestrator after pytest run
    execution_result: ExecutionResult | None = None

    # Set by ReportAgent
    report_path: str | None = None

    # Set by SelfHealingAgent
    self_healing_results: list[dict[str, Any]] = Field(default_factory=list)

    # Accumulated errors (non-fatal warnings from any agent)
    pipeline_errors: list[str] = Field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.pipeline_errors.append(message)


# ──────────────────────────────────────────────────────────────────────────────
# BaseAgent
# ──────────────────────────────────────────────────────────────────────────────

class BaseAgent(ABC):
    """Abstract base for all ATF agents.

    Subclasses MUST implement:
        - agent_name (property) → used to locate agents/<name>.md
        - run(context)          → mutates context in place, returns it
    """

    def __init__(
        self,
        config: Config,
        llm: LLMProvider,
        vector_store: ATFVectorStore,
        bus: MessageBus,
    ) -> None:
        self._config = config
        self._llm = llm
        self._vector_store = vector_store
        self._bus = bus
        self._system_prompt = self._load_system_prompt()
        self._logger = logging.getLogger(
            f"atf.agents.{self.agent_name}"
        )

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique snake_case name — must match agents/<name>.md filename."""

    @abstractmethod
    def run(self, context: PipelineContext) -> PipelineContext:
        """Execute the agent's work.

        Agents MUST:
          - Read required data from context.
          - Write their output fields back onto context.
          - Post at least one Message to self._bus with their result.
          - Return the mutated context.

        Agents MUST NOT:
          - Raise exceptions for non-fatal issues (use context.add_error).
          - Call other agents directly (always go through the Orchestrator).
        """

    # ------------------------------------------------------------------
    # Helpers available to all agents
    # ------------------------------------------------------------------

    def _load_system_prompt(self) -> str:
        """Load the agent's system prompt from agents/<agent_name>.md."""
        agents_dir = (
            Path(__file__).parent.parent.parent / "agents"
        )
        prompt_file = agents_dir / f"{self.agent_name}.md"
        if not prompt_file.exists():
            raise AgentError(
                f"System prompt file not found for agent '{self.agent_name}'.",
                details={"expected_path": str(prompt_file)},
            )
        return prompt_file.read_text(encoding="utf-8")

    def _post(
        self,
        context: PipelineContext,
        message_type: str,
        payload: dict,
        recipient: str = "orchestrator",
    ) -> None:
        """Convenience wrapper: post a Message to the bus."""
        self._bus.post(
            Message(
                sender=self.agent_name,
                recipient=recipient,
                message_type=message_type,
                payload=payload,
                correlation_id=context.correlation_id,
            )
        )

    def __repr__(self) -> str:
        return f"<Agent: {self.agent_name}>"
