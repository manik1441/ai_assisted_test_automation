"""Log Agent — centralized structured logging for the pipeline.

Responsibilities:
- Configure structlog for the entire framework at startup.
- Provide a singleton logger that all agents can access.
- Write JSON log entries to the configured output directory.

Design note:
  LogAgent does NOT implement run() in the typical agent sense.
  It is called by the Orchestrator at startup to configure logging,
  and then each agent writes to the logger directly via self._logger.
  The run() method is provided for API consistency — it emits a
  pipeline-level summary log entry.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.config import LoggingConfig


def configure_logging(config: LoggingConfig) -> None:
    """Configure structlog and stdlib logging for the framework.

    Must be called once at application startup (Orchestrator.__init__).
    """
    log_dir = Path(config.output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.level.upper(), logging.INFO)

    # Shared processors
    shared_processors: list = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if config.format == "json":
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Root logger — writes to both file (JSON) and stderr (console)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # File handler — rotating, 10 MB max, 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "atf.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)


class LogAgent(BaseAgent):
    """Centralized logging agent.

    Unlike other agents, LogAgent.run() emits a structured pipeline-
    summary log entry rather than doing LLM work.
    """

    @property
    def agent_name(self) -> str:
        return "log_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Emit a final structured pipeline summary log entry."""
        self._logger.info(
            "Pipeline summary",
            extra={
                "correlation_id": context.correlation_id,
                "test_type": context.test_type,
                "intent": context.intent,
                "scripts_generated": len(context.generated_scripts),
                "scripts_reviewed": len(context.review_results),
                "pipeline_errors": context.pipeline_errors,
            },
        )

        self._post(
            context=context,
            message_type="pipeline_logged",
            payload={"correlation_id": context.correlation_id},
        )

        return context
