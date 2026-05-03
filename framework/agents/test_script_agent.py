"""Test Script Agent — converts scenarios to executable pytest scripts.

Responsibilities:
- Receive test_scenarios from PipelineContext.
- Build a prompt that includes all scenarios as JSON context.
- Call LLM with test_script_agent.md system prompt.
- Parse the returned scripts list.
- Write generated_scripts to PipelineContext.
- Save each script to disk under execution.output_dir.
- Persist scripts to vector store for future reuse.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from framework.core.base_agent import BaseAgent, GeneratedScript, PipelineContext
from framework.core.exceptions import TestGenerationError

logger = logging.getLogger(__name__)


class TestScriptAgent(BaseAgent):
    """Generates pytest-compatible test scripts from structured scenarios."""

    @property
    def agent_name(self) -> str:
        return "test_script_agent"

    def run(self, context: PipelineContext) -> PipelineContext:
        """Generate scripts for all scenarios and enrich the context.

        Sets:
            context.generated_scripts — list of GeneratedScript objects
        """
        if not context.test_scenarios:
            context.add_error(
                "TestScriptAgent: no scenarios available to generate scripts."
            )
            self._logger.warning("No scenarios found — skipping script generation.")
            return context

        self._logger.info(
            "Generating scripts for %d scenario(s).", len(context.test_scenarios)
        )

        prompt = self._build_prompt(context)

        try:
            raw_response: str = self._llm.generate(
                prompt=prompt,
                system_prompt=self._system_prompt,
            )
        except Exception as exc:
            raise TestGenerationError(
                f"TestScriptAgent LLM call failed: {exc}",
                details={"correlation_id": context.correlation_id},
            ) from exc

        # Extract JSON metadata
        import re
        import json
        
        start_idx = raw_response.find("{")
        if start_idx == -1:
             raise TestGenerationError("Could not find JSON metadata in LLM response.")
             
        brace_count = 0
        end_idx = -1
        in_string = False
        escape = False
        for i in range(start_idx, len(raw_response)):
            char = raw_response[i]
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
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
                        
        if end_idx == -1:
             raise TestGenerationError("Could not find balanced JSON metadata in LLM response.")
             
        json_str = raw_response[start_idx:end_idx+1]
        try:
            # Basic sanitize
            sanitized = json_str.replace("\\'", "'")
            result = json.loads(sanitized)
        except json.JSONDecodeError as exc:
            raise TestGenerationError(f"Failed to parse JSON metadata: {exc}\nRaw: {json_str[:100]}...")

        raw_scripts: list[dict] = result.get("scripts", [])
        if not raw_scripts:
            raise TestGenerationError(
                "TestScriptAgent: LLM returned no scripts metadata.",
                details={"raw_result": str(result)[:500]},
            )
            
        # Extract Python code blocks
        blocks = re.findall(r'```([a-z]*)\s*(.*?)\s*```', raw_response, re.DOTALL | re.IGNORECASE)
        
        python_blocks = []
        for lang, content in blocks:
             if lang.strip().lower() == 'json':
                  continue
             if content.strip().startswith('{') and content.strip().endswith('}'):
                  continue # likely a json block without tag
             python_blocks.append(content)

        if len(python_blocks) < len(raw_scripts):
             self._logger.warning(f"Mismatch: {len(raw_scripts)} scripts in JSON, {len(python_blocks)} python blocks found.")
             while len(python_blocks) < len(raw_scripts):
                  python_blocks.append("# Error: Could not extract code block for this script.")

        output_dir = Path(self._config.execution.output_dir)
        
        generated: list[GeneratedScript] = []
        for i, raw in enumerate(raw_scripts):
            script_id = str(uuid.uuid4())
            filename = raw.get("filename", f"test_generated_{script_id[:8]}.py")
            content = python_blocks[i].strip()
            test_type = raw.get("test_type", context.test_type or "ui")

            script = GeneratedScript(
                script_id=script_id,
                filename=filename,
                content=content,
                test_type=test_type,
                task_id=context.tasks[0].task_id if context.tasks else "none",
            )
            generated.append(script)

            # Organize into subfolders: tests/UI, tests/API, etc.
            type_subdir = output_dir / test_type.upper()
            type_subdir.mkdir(parents=True, exist_ok=True)
            
            # Write to disk
            script_path = type_subdir / filename
            script_path.write_text(content, encoding="utf-8")
            self._logger.info("Wrote script: %s", script_path)

            # Persist to vector store (best-effort)
            try:
                self._vector_store.store_test_script(
                    script_id=script_id,
                    script=content,
                    metadata={
                        "filename": filename,
                        "test_type": test_type,
                        "intent": context.intent or "",
                    },
                )
            except Exception as exc:
                self._logger.warning(
                    "Failed to persist script to vector store: %s", exc
                )

        context.generated_scripts = generated

        self._post(
            context=context,
            message_type="scripts_generated",
            payload={
                "script_count": len(generated),
                "filenames": [s.filename for s in generated],
            },
        )

        self._logger.info(
            "TestScriptAgent produced %d script(s).", len(generated)
        )
        return context

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, context: PipelineContext) -> str:
        import json

        lines = [
            f"Test Type: {context.test_type}",
            f"Intent: {context.intent}",
            "",
            "Scenarios (JSON):",
            json.dumps(context.test_scenarios, indent=2),
        ]

        if context.tasks:
            lines.insert(2, f"Tasks: {[t.description for t in context.tasks]}")

        return "\n".join(lines)
