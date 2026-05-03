"""CI/CD Agent — generates pipeline YAML configuration files.

Responsibilities:
- Read cicd provider from Config.
- Call LLM with cicd_agent.md system prompt.
- Parse the returned YAML content.
- Write the YAML file to the configured output directory.
- Return the file path in the bus message.
"""

from __future__ import annotations

import logging
from pathlib import Path

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.exceptions import CICDGenerationError

logger = logging.getLogger(__name__)

_PROVIDER_FILENAMES = {
    "github_actions": "atf-tests.yml",
    "gitlab_ci": ".gitlab-ci.yml",
}


class CICDAgent(BaseAgent):
    """Generates CI/CD pipeline YAML for the configured provider."""

    @property
    def agent_name(self) -> str:
        return "cicd_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Generate a CI/CD pipeline configuration file.

        Output is written to cicd.output_dir from config.yaml.
        """
        provider = self._config.cicd.provider
        self._logger.info("Generating CI/CD config for provider: %s", provider)

        prompt = self._build_prompt(provider, context)

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise CICDGenerationError(
                f"CICDAgent LLM call failed: {exc}",
                details={"provider": provider},
            ) from exc

        yaml_content: str = result.get("content", "")
        if not yaml_content:
            raise CICDGenerationError(
                "CICDAgent: LLM returned empty pipeline content.",
                details={"provider": provider},
            )

        filename = result.get(
            "filename",
            _PROVIDER_FILENAMES.get(provider, "atf-pipeline.yml"),
        )

        output_path = Path(self._config.cicd.output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_content, encoding="utf-8")

        self._logger.info("CI/CD config written to: %s", output_path)

        self._post(
            context=context,
            message_type="cicd_generated",
            payload={"provider": provider, "file": str(output_path)},
        )

        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, provider: str, context: PipelineContext) -> str:
        return (
            f"Generate a complete CI/CD pipeline configuration for provider: {provider}.\n"
            f"The pipeline must:\n"
            f"  - Use Python 3.12\n"
            f"  - Install from requirements.txt\n"
            f"  - Install Playwright browsers (chromium)\n"
            f"  - Run: pytest {self._config.execution.output_dir} "
            f"--alluredir={self._config.reporting.report_dir}/allure-results\n"
            f"  - Upload Allure results as artifacts on both pass and fail\n"
            f"  - Reference BASE_URL and OPENROUTER_API_KEY as environment secrets\n"
            f"The test suite was generated for: {context.intent or 'automated tests'}\n"
        )
