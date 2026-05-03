"""In-process message bus for inter-agent communication.

Design (V1):
- All communication is synchronous and in-process (no network, no queue broker).
- Agents post Message objects; the bus appends them to an ordered log.
- The Orchestrator (and any agent) can read the full log or filter by type/sender.
- Correlation IDs link all messages belonging to the same pipeline run.

V2 note: Replace _messages list with a proper queue broker (Redis Streams /
RabbitMQ) without changing the Agent API — only MessageBus internals change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


# ──────────────────────────────────────────────────────────────────────────────
# Message model
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Message:
    """Immutable message exchanged between agents."""

    sender: str              # Agent name that produced this message
    recipient: str           # Intended consumer ("orchestrator", "all", etc.)
    message_type: str        # Semantic type: "intent", "tasks", "scripts", etc.
    payload: dict            # Free-form content — validated by each consumer
    correlation_id: str      # Links all messages in a single pipeline run
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Message bus
# ──────────────────────────────────────────────────────────────────────────────

class MessageBus:
    """Simple in-process event bus.

    Usage:
        bus = MessageBus()
        bus.post(Message(sender="lead_agent", ...))
        msgs = bus.get_by_type("intent")
    """

    def __init__(self) -> None:
        self._messages: list[Message] = []
        self._subscribers: dict[str, list[Callable[[Message], None]]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def post(self, message: Message) -> None:
        """Append a message to the bus and notify subscribers."""
        self._messages.append(message)
        for callback in self._subscribers.get(message.message_type, []):
            callback(message)
        for callback in self._subscribers.get("*", []):
            callback(message)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_all(self, correlation_id: str | None = None) -> list[Message]:
        """Return all messages, optionally filtered by correlation_id."""
        if correlation_id is None:
            return list(self._messages)
        return [m for m in self._messages if m.correlation_id == correlation_id]

    def get_by_type(
        self,
        message_type: str,
        correlation_id: str | None = None,
    ) -> list[Message]:
        """Return messages filtered by type, optionally by correlation_id."""
        msgs = [m for m in self._messages if m.message_type == message_type]
        if correlation_id:
            msgs = [m for m in msgs if m.correlation_id == correlation_id]
        return msgs

    def get_latest(
        self,
        message_type: str,
        correlation_id: str | None = None,
    ) -> Message | None:
        """Return the most recent message of a given type."""
        msgs = self.get_by_type(message_type, correlation_id)
        return msgs[-1] if msgs else None

    # ------------------------------------------------------------------
    # Subscribe (optional reactive pattern)
    # ------------------------------------------------------------------

    def subscribe(self, message_type: str, callback: Callable[[Message], None]) -> None:
        """Register a callback triggered whenever a message_type is posted.

        Use message_type="*" to subscribe to all messages.
        """
        self._subscribers.setdefault(message_type, []).append(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all messages (use between pipeline runs in tests)."""
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)
