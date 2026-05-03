"""Framework configuration management.

Loads config from YAML, then applies environment variable overrides.
Environment variables always win over config.yaml values.

Usage:
    from framework.core.config import load_config
    config = load_config()            # uses default path
    config = load_config("my.yaml")   # custom path
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from framework.core.exceptions import ConfigurationError

load_dotenv()


# ──────────────────────────────────────────────────────────────────────────────
# Sub-config dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    provider: str = "openrouter"
    model: str = "openai/gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 4096
    base_url: str = "https://openrouter.ai/api/v1"


@dataclass
class ExecutionConfig:
    browser: str = "chromium"
    headless: bool = True
    self_healing: bool = True
    timeout_ms: int = 30000
    output_dir: str = "./tests"


@dataclass
class ReportingConfig:
    allure: bool = True
    attach_screenshots: bool = True
    attach_logs: bool = True
    attach_api_responses: bool = True
    report_dir: str = "./reports"


@dataclass
class VectorStoreConfig:
    provider: str = "chroma"
    persist_directory: str = "./vector_store"
    collection_prefix: str = "atf"


@dataclass
class JiraConfig:
    enabled: bool = True
    # Toggle: False = read-only | True = read + write back
    write_back: bool = False
    base_url: str = ""
    project_key: str = ""


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"
    output_dir: str = "./logs"


@dataclass
class CICDConfig:
    provider: str = "github_actions"
    output_dir: str = "./.github/workflows"


# ──────────────────────────────────────────────────────────────────────────────
# Root Config
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    jira: JiraConfig = field(default_factory=JiraConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    cicd: CICDConfig = field(default_factory=CICDConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        """Load a Config from a YAML file, then apply env overrides."""
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {config_path}",
                details={"path": str(config_path)},
            )

        with config_path.open(encoding="utf-8") as fh:
            raw: dict = yaml.safe_load(fh) or {}

        if not isinstance(raw, dict):
            raise ConfigurationError(
                "config.yaml must be a YAML mapping at the top level."
            )

        config = cls()

        # Map each YAML section to its dataclass
        _section_map = {
            "llm": (LLMConfig, "llm"),
            "execution": (ExecutionConfig, "execution"),
            "reporting": (ReportingConfig, "reporting"),
            "vector_store": (VectorStoreConfig, "vector_store"),
            "jira": (JiraConfig, "jira"),
            "logging": (LoggingConfig, "logging"),
            "cicd": (CICDConfig, "cicd"),
        }

        for yaml_key, (klass, attr) in _section_map.items():
            if section := raw.get(yaml_key):
                try:
                    setattr(config, attr, klass(**section))
                except TypeError as exc:
                    raise ConfigurationError(
                        f"Invalid keys in config section '{yaml_key}': {exc}",
                        details={"section": yaml_key},
                    ) from exc

        config._apply_env_overrides()
        return config

    def _apply_env_overrides(self) -> None:
        """Environment variables override config.yaml values.

        Supported overrides:
            JIRA_BASE_URL      → jira.base_url
            JIRA_PROJECT_KEY   → jira.project_key
        """
        if jira_url := os.getenv("JIRA_BASE_URL"):
            self.jira.base_url = jira_url
        if jira_key := os.getenv("JIRA_PROJECT_KEY"):
            self.jira.project_key = jira_key


# ──────────────────────────────────────────────────────────────────────────────
# Public factory
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent.parent / "configs" / "config.yaml"
)


def load_config(path: str | Path | None = None) -> Config:
    """Load and return the framework configuration.

    Priority:
        1. ``path`` argument
        2. ``ATF_CONFIG_PATH`` environment variable
        3. Default: ``configs/config.yaml`` relative to project root
    """
    resolved = path or os.getenv("ATF_CONFIG_PATH") or _DEFAULT_CONFIG_PATH
    return Config.from_yaml(resolved)
