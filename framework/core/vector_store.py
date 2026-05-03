"""ChromaDB vector store wrapper for ATF memory layer.

Three named collections (all prefixed with config.collection_prefix):
  - prompts           : historical prompts + their classified test types
  - generated_tests   : previously generated test scripts (for reuse/pattern)
  - locator_strategies: UI element locators used by the UI agent

All methods raise VectorStoreError on failure so callers never see raw
ChromaDB exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings

from framework.core.config import VectorStoreConfig
from framework.core.exceptions import VectorStoreError


# ──────────────────────────────────────────────────────────────────────────────
# Value objects
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class VectorEntry:
    id: str
    content: str
    metadata: dict[str, Any]


@dataclass
class SearchResult:
    entry: VectorEntry
    distance: float


# ──────────────────────────────────────────────────────────────────────────────
# Collection name constants
# ──────────────────────────────────────────────────────────────────────────────

_COL_PROMPTS = "prompts"
_COL_TESTS = "generated_tests"
_COL_LOCATORS = "locator_strategies"


# ──────────────────────────────────────────────────────────────────────────────
# ATF Vector Store
# ──────────────────────────────────────────────────────────────────────────────

class ATFVectorStore:
    """Persistent ChromaDB vector store.

    Usage:
        store = ATFVectorStore(config.vector_store)
        store.store_prompt("id-1", "Test login page", test_type="ui")
        results = store.find_similar_prompts("Login with valid credentials")
    """

    def __init__(self, config: VectorStoreConfig) -> None:
        self._config = config
        try:
            self._client = chromadb.PersistentClient(
                path=config.persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to initialize ChromaDB: {exc}",
                details={"persist_directory": config.persist_directory},
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _col_name(self, suffix: str) -> str:
        return f"{self._config.collection_prefix}_{suffix}"

    def _get_or_create(self, suffix: str) -> chromadb.Collection:
        try:
            return self._client.get_or_create_collection(
                name=self._col_name(suffix),
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to access collection '{suffix}': {exc}"
            ) from exc

    @staticmethod
    def _parse_results(results: dict) -> list[SearchResult]:
        """Convert raw ChromaDB query results into SearchResult list."""
        output: list[SearchResult] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for entry_id, doc, meta, dist in zip(ids, docs, metas, dists):
            output.append(
                SearchResult(
                    entry=VectorEntry(id=entry_id, content=doc, metadata=meta or {}),
                    distance=dist,
                )
            )
        return output

    # ------------------------------------------------------------------
    # Prompt memory
    # ------------------------------------------------------------------

    def store_prompt(
        self,
        prompt_id: str,
        prompt: str,
        test_type: str,
        metadata: dict | None = None,
    ) -> None:
        """Persist a prompt and its classified test type."""
        col = self._get_or_create(_COL_PROMPTS)
        meta = {"test_type": test_type, **(metadata or {})}
        try:
            col.upsert(ids=[prompt_id], documents=[prompt], metadatas=[meta])
        except Exception as exc:
            raise VectorStoreError(f"Failed to store prompt: {exc}") from exc

    def find_similar_prompts(
        self, prompt: str, n_results: int = 3
    ) -> list[SearchResult]:
        """Return the N most similar historical prompts."""
        col = self._get_or_create(_COL_PROMPTS)
        try:
            results = col.query(query_texts=[prompt], n_results=n_results)
            return self._parse_results(results)
        except Exception as exc:
            raise VectorStoreError(f"Failed to query prompts: {exc}") from exc

    # ------------------------------------------------------------------
    # Generated test memory
    # ------------------------------------------------------------------

    def store_test_script(
        self,
        script_id: str,
        script: str,
        metadata: dict | None = None,
    ) -> None:
        """Persist a generated test script for future reuse."""
        col = self._get_or_create(_COL_TESTS)
        try:
            col.upsert(
                ids=[script_id],
                documents=[script],
                metadatas=[metadata or {}],
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to store test script: {exc}") from exc

    def find_similar_tests(
        self, prompt: str, n_results: int = 3
    ) -> list[SearchResult]:
        """Return previously generated tests similar to the given prompt."""
        col = self._get_or_create(_COL_TESTS)
        try:
            results = col.query(query_texts=[prompt], n_results=n_results)
            return self._parse_results(results)
        except Exception as exc:
            raise VectorStoreError(f"Failed to query test scripts: {exc}") from exc

    # ------------------------------------------------------------------
    # Locator strategy memory
    # ------------------------------------------------------------------

    def store_locator(
        self,
        locator_id: str,
        description: str,
        selector: str,
        metadata: dict | None = None,
    ) -> None:
        """Persist a UI locator strategy for the UI agent to reuse."""
        col = self._get_or_create(_COL_LOCATORS)
        meta = {"selector": selector, **(metadata or {})}
        try:
            col.upsert(
                ids=[locator_id],
                documents=[description],
                metadatas=[meta],
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to store locator: {exc}") from exc

    def find_similar_locators(
        self, description: str, n_results: int = 3
    ) -> list[SearchResult]:
        """Return known locators similar to the given element description."""
        col = self._get_or_create(_COL_LOCATORS)
        try:
            results = col.query(query_texts=[description], n_results=n_results)
            return self._parse_results(results)
        except Exception as exc:
            raise VectorStoreError(f"Failed to query locators: {exc}") from exc
