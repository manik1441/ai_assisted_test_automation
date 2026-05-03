"""UI Agent — Playwright DOM analysis and test scenario generation.

Responsibilities:
- Receive test intent (from PipelineContext).
- Call LLM with ui_agent.md system prompt.
- Parse and validate the scenario JSON.
- Write test_scenarios back to PipelineContext.
- Persist locator strategies to vector store.
"""

from __future__ import annotations

import logging

from framework.core.base_agent import BaseAgent, PipelineContext
from framework.core.exceptions import AgentError

logger = logging.getLogger(__name__)


class UIAgent(BaseAgent):
    """Generates Playwright UI test scenarios from test intent."""

    @property
    def agent_name(self) -> str:
        return "ui_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Generate UI test scenarios and enrich the context.

        Sets:
            context.test_scenarios — list of scenario dicts
        """
        if context.test_type != "ui":
            self._logger.debug(
                "UIAgent skipped: test_type=%s", context.test_type
            )
            return context

        self._logger.info(
            "Generating UI scenarios for intent: %s", context.intent
        )

        prompt = self._build_prompt(context)

        try:
            result: dict = self._llm.generate_json(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise AgentError(
                f"UIAgent LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        scenarios: list[dict] = result.get("scenarios", [])
        if not scenarios:
            context.add_error("UIAgent: LLM returned no scenarios.")
            self._logger.warning("UIAgent returned empty scenarios.")

        # Attach page_object_class to each scenario for TestScriptAgent
        pom_class = result.get("page_object_class", "GeneratedPage")
        for scenario in scenarios:
            scenario["page_object_class"] = pom_class

        context.test_scenarios = scenarios

        # Persist locator strategies to vector store for future reuse
        self._store_locators(scenarios)

        self._post(
            context=context,
            message_type="ui_scenarios",
            payload={
                "scenario_count": len(scenarios),
                "page_object_class": pom_class,
            },
        )

        self._logger.info("UIAgent generated %d scenario(s).", len(scenarios))
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, context: PipelineContext) -> str:
        lines = [
            f"Test Intent: {context.intent}",
            f"Raw Prompt: {context.raw_prompt}",
        ]

        # Include task descriptions if the planner has run
        if context.tasks:
            lines.append("\nTasks to cover:")
            for task in context.tasks:
                lines.append(f"  - {task.description}")

        # Fetch DOM context to avoid hallucinating locators
        dom_context = self._fetch_dom_context(f"{context.raw_prompt} {context.intent}")
        if dom_context:
             lines.append("\n" + dom_context)
             
        return "\n".join(lines)

    def _fetch_dom_context(self, prompt_text: str) -> str:
        import re
        from playwright.sync_api import sync_playwright

        urls = re.findall(r'(https?://[^\s]+)', prompt_text)
        url = urls[0] if urls else None
        
        if not url:
             domain_match = re.search(r'\b([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b', prompt_text)
             if domain_match and domain_match.group(1).lower() not in ["json", "py", "md", "yaml"]:
                  url = "https://" + domain_match.group(1)
                  
        if not url:
             return ""
             
        self._logger.info(f"Attempting to fetch DOM context from {url}")
        try:
             with sync_playwright() as p:
                  browser = p.chromium.launch(headless=True)
                  page = browser.new_page()
                  page.goto(url, timeout=15000)
                  page.wait_for_load_state("domcontentloaded")
                  
                  elements = page.evaluate("""() => {
                      const interactive = Array.from(document.querySelectorAll('button, input, a, select, textarea, [role="button"], [aria-label]'));
                      return interactive.map(el => {
                           let text = el.innerText || el.value || el.placeholder || el.name || el.id || el.getAttribute('aria-label') || '';
                           let type = el.tagName.toLowerCase();
                           if (type === 'input') type += ' ' + (el.type || 'text');
                           let cleanedText = text.trim().replace(/\\s+/g, ' ').substring(0, 60);
                           return cleanedText ? (type + ' -> ' + cleanedText) : '';
                      }).filter(e => e.length > 0);
                  }""")
                  browser.close()
                  
                  if elements:
                      # Remove duplicates and limit to top 100 elements
                      unique_elements = list(dict.fromkeys(elements))[:100]
                      return "Available interactive elements on target page (Use these for exact locators):\n- " + "\n- ".join(unique_elements)
        except Exception as exc:
             self._logger.warning(f"Failed to fetch DOM context from {url}: {exc}")
             
        return ""

    def _store_locators(self, scenarios: list[dict]) -> None:
        """Persist locator info from scenarios to vector store."""
        for scenario in scenarios:
            for step in scenario.get("steps", []):
                locator = step.get("locator")
                action = step.get("action", "")
                if locator:
                    try:
                        locator_id = (
                            f"{scenario.get('scenario_id', 'unknown')}_{action}"
                        )
                        description = (
                            f"{action} on element using {locator} "
                            f"in scenario '{scenario.get('name', '')}'"
                        )
                        self._vector_store.store_locator(
                            locator_id=locator_id,
                            description=description,
                            selector=locator,
                            metadata={"scenario": scenario.get("name", "")},
                        )
                    except Exception as exc:
                        self._logger.warning(
                            "Failed to store locator in vector store: %s", exc
                        )
