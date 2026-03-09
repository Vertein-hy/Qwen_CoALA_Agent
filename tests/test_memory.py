from __future__ import annotations

import json
import sys
import types


class _DefaultEmbeddingFunction:
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class _FakeCollection:
    def __init__(self) -> None:
        self._docs: list[str] = []
        self._ids: list[str] = []

    def add(
        self,
        documents: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        for idx, doc in enumerate(documents):
            self._docs.append(doc)
            self._ids.append(ids[idx] if ids else f"mem_{len(self._ids)}")

    def query(self, query_texts: list[str], n_results: int = 3) -> dict:
        del query_texts
        picked_docs = self._docs[-n_results:][::-1]
        picked_ids = self._ids[-n_results:][::-1]
        return {
            "documents": [picked_docs],
            "ids": [picked_ids],
            "distances": [[0.1 + i * 0.1 for i in range(len(picked_docs))]],
        }

    def count(self) -> int:
        return len(self._docs)


class _FakePersistentClient:
    def __init__(self, path: str) -> None:
        self.path = path
        self.collection = _FakeCollection()

    def get_or_create_collection(self, name: str, embedding_function: object) -> _FakeCollection:
        del name, embedding_function
        return self.collection


try:
    import chromadb as _chromadb  # type: ignore
except Exception:
    _chromadb = types.ModuleType("chromadb")
    sys.modules["chromadb"] = _chromadb

if not hasattr(_chromadb, "PersistentClient"):
    _chromadb.PersistentClient = _FakePersistentClient

embedding_stub = sys.modules.get("chromadb.utils.embedding_functions")
if embedding_stub is None:
    chromadb_utils_stub = types.ModuleType("chromadb.utils")
    embedding_stub = types.ModuleType("chromadb.utils.embedding_functions")
    chromadb_utils_stub.embedding_functions = embedding_stub
    _chromadb.utils = chromadb_utils_stub
    sys.modules["chromadb.utils"] = chromadb_utils_stub
    sys.modules["chromadb.utils.embedding_functions"] = embedding_stub

if not hasattr(embedding_stub, "DefaultEmbeddingFunction"):
    embedding_stub.DefaultEmbeddingFunction = _DefaultEmbeddingFunction

from config.settings import MemoryConfig
from memory.vector_store import MemorySystem


def test_search_returns_structured_payload(tmp_path) -> None:
    memory = MemorySystem(
        MemoryConfig(
            vector_db_path=tmp_path / "chroma_db",
            enable_event_log=False,
            event_log_dir=tmp_path / "logs",
        )
    )
    memory.add("alpha", trace_id="tr_case_1")
    memory.add("beta", trace_id="tr_case_1")

    result = memory.search("a", n_results=2, trace_id="tr_case_1", query_type="task_context")

    assert set(result.keys()) == {"documents", "memory_ids", "distances", "query_id"}
    assert len(result["documents"]) == 2
    assert len(result["memory_ids"]) == 2
    assert len(result["distances"]) == 2
    assert result["query_id"]


def test_memory_events_are_written_with_shared_trace_id(tmp_path) -> None:
    event_dir = tmp_path / "memory_events"
    memory = MemorySystem(
        MemoryConfig(
            vector_db_path=tmp_path / "chroma_db",
            enable_event_log=True,
            event_log_dir=event_dir,
        )
    )

    trace_id = "tr_shared_123"
    memory.add("hello", trace_id=trace_id, write_reason="final_answer")
    memory.search("hello", n_results=1, trace_id=trace_id, query_type="task_context")

    event_files = list(event_dir.glob("*.jsonl"))
    assert len(event_files) == 1

    records = [json.loads(line) for line in event_files[0].read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert records[0]["event_type"] == "memory_write"
    assert records[1]["event_type"] == "memory_search"
    assert records[0]["trace_id"] == trace_id
    assert records[1]["trace_id"] == trace_id
