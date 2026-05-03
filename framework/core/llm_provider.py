"""LLM Provider abstraction layer.

Design:
- LLMProvider is an ABC with two methods: generate() and generate_json().
- OpenRouterProvider is the concrete V1 implementation (OpenAI-compatible API).
- create_llm_provider() is the factory — reads provider from Config.

Adding a new provider (e.g. Ollama):
    1. Subclass LLMProvider.
    2. Implement generate() and generate_json().
    3. Add a branch to create_llm_provider().
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from framework.core.config import Config, LLMConfig
from framework.core.exceptions import LLMProviderError


# ──────────────────────────────────────────────────────────────────────────────
# Abstract base
# ──────────────────────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate a text completion from a user prompt."""

    @abstractmethod
    def generate_json(self, prompt: str, system_prompt: str = "") -> dict:
        """Generate a structured JSON object from a user prompt.

        Implementations must guarantee the return value is a valid Python dict.
        """


# ──────────────────────────────────────────────────────────────────────────────
# OpenRouter implementation
# ──────────────────────────────────────────────────────────────────────────────

class OpenRouterProvider(LLMProvider):
    """OpenRouter LLM provider using the OpenAI-compatible REST API.

    Reads OPENROUTER_API_KEY from the environment.
    Model, temperature, and max_tokens come from LLMConfig.
    """

    # Markdown fence pattern that models sometimes output despite instructions
    _FENCE_RE = re.compile(r"```(?:json)?\s*|\s*```", re.IGNORECASE)

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "OPENROUTER_API_KEY environment variable is not set.",
                details={"required_env": "OPENROUTER_API_KEY"},
            )
        self._client = OpenAI(api_key=api_key, base_url=config.base_url)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Call OpenRouter and return the raw text response."""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=messages,
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMProviderError(
                f"OpenRouter API call failed: {exc}",
                details={"model": self._config.model},
            ) from exc

    def generate_json(self, prompt: str, system_prompt: str = "") -> dict:
        """Call OpenRouter and parse the response as JSON.

        A JSON instruction is appended to the system prompt so the model
        returns only a valid JSON object. If parsing still fails, a
        LLMProviderError is raised with the raw output for debugging.
        """
        json_instruction = (
            "\n\nIMPORTANT: Respond with a single valid JSON object only. "
            "Do not include markdown code fences, prose, or any text outside "
            "the JSON object."
        )
        full_system = (system_prompt or "") + json_instruction
        raw = self.generate(prompt, system_prompt=full_system)

        # Find the start of the JSON block (either { or [)
        start_obj = raw.find("{")
        start_list = raw.find("[")
        
        start_idx = -1
        is_array = False
        if start_obj != -1 and start_list != -1:
             start_idx = min(start_obj, start_list)
             is_array = (start_idx == start_list)
        elif start_obj != -1:
             start_idx = start_obj
        elif start_list != -1:
             start_idx = start_list
             is_array = True
             
        extracted = raw
        if start_idx != -1:
             brace_count = 0
             end_idx = -1
             in_string = False
             escape = False
             open_char = '[' if is_array else '{'
             close_char = ']' if is_array else '}'
             
             for i in range(start_idx, len(raw)):
                 char = raw[i]
                 if escape:
                     escape = False
                     continue
                 if char == '\\':
                     escape = True
                     continue
                 if char == '"':
                     in_string = not in_string
                     continue
                 
                 if not in_string:
                     if char == open_char:
                         brace_count += 1
                     elif char == close_char:
                         brace_count -= 1
                         if brace_count == 0:
                             end_idx = i
                             break
                             
             if end_idx != -1:
                  extracted = raw[start_idx:end_idx+1]

        # Strip any markdown fences the model may have added anyway inside the extraction
        cleaned = self._FENCE_RE.sub("", extracted).strip()

        # Sanitize common LLM JSON errors:
        # 1. Invalid single quote escapes (\')
        sanitized = cleaned.replace("\\'", "'")

        try:
            return json.loads(sanitized)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"LLM returned invalid JSON: {exc}",
                details={"raw_output": raw[:500]},
            ) from exc


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_llm_provider(config: Config) -> LLMProvider:
    """Return the LLM provider instance configured in config.yaml."""
    if config.llm.provider == "openrouter":
        return OpenRouterProvider(config.llm)

    raise LLMProviderError(
        f"Unsupported LLM provider: '{config.llm.provider}'",
        details={"supported_providers": ["openrouter"]},
    )
