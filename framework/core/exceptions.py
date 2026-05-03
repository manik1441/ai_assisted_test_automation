"""Custom exceptions for the Agentic TestGen Framework (ATF).

All exceptions inherit from ATFBaseException so callers can
catch the entire ATF error hierarchy with a single except clause.
"""


class ATFBaseException(Exception):
    """Base exception for all ATF errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | details={self.details}"
        return self.message


# --- Configuration ---

class ConfigurationError(ATFBaseException):
    """Raised when framework configuration is invalid or missing."""


# --- LLM ---

class LLMProviderError(ATFBaseException):
    """Raised when an LLM API call fails or returns unexpected output."""


# --- Agents ---

class AgentError(ATFBaseException):
    """Raised when an agent encounters an unrecoverable error."""


class ClassificationError(ATFBaseException):
    """Raised when test type classification fails."""


class TestGenerationError(ATFBaseException):
    """Raised when test script generation fails."""


class ReviewError(ATFBaseException):
    """Raised when the review agent encounters an error."""


# --- Execution ---

class ExecutionError(ATFBaseException):
    """Raised when pytest / Playwright test execution fails."""


# --- Vector Store ---

class VectorStoreError(ATFBaseException):
    """Raised when ChromaDB operations fail."""


# --- Integrations ---

class JiraConnectorError(ATFBaseException):
    """Raised when Jira API operations fail."""


class CICDGenerationError(ATFBaseException):
    """Raised when CI/CD configuration generation fails."""
