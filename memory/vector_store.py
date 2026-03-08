"""Vector store implementation for long-term memory.

Responsibilities:
- Persist and query semantic memories via Chroma.
- Emit optional JSONL events for offline reward attribution.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from config.settings import MemoryConfig, load_config


@dataclass(frozen=True)
class SearchResult:
    documents: list[str]
    memory_ids: list[str]
    distances: list[float]
    query_id: str

    def as_dict(self) -> dict:
        return {
            "documents": self.documents,
            "memory_ids": self.memory_ids,
            "distances": self.distances,
            "query_id": self.query_id,
        }


class MemorySystem:
    """Long-term memory storage with structured outputs and event logging."""

    def __init__(self, config: MemoryConfig | None = None):
        app_cfg = load_config()
        self.config = config or app_cfg.memory

        self.config.vector_db_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.config.vector_db_path))
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name="evo_memories",
            embedding_function=self.emb_fn,
        )

        if self.config.enable_event_log:
            self.config.event_log_dir.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        text: str,
        metadata: dict | None = None,
        trace_id: str | None = None,
        write_reason: str | None = None,
        source: str = "self_generated",
        score_snapshot: dict | None = None,
    ) -> str:
        """Write one memory item and return generated memory_id."""

        resolved_trace_id = self._normalize_trace_id(trace_id)
        final_metadata = metadata or {"type": "conversation"}
        memory_id = str(uuid.uuid4())

        self.collection.add(
            documents=[text],
            metadatas=[final_metadata],
            ids=[memory_id],
        )

        self._log_event(
            {
                "event_type": "memory_write",
                "event_ts": self._now_iso(),
                "trace_id": resolved_trace_id,
                "memory_id": memory_id,
                "source": source,
                "write_reason": write_reason,
                "metadata": final_metadata,
                "text_len": len(text),
                "write_accepted": True,
                "score_snapshot": score_snapshot,
            }
        )
        return memory_id

    def search(
        self,
        query: str,
        n_results: int = 3,
        trace_id: str | None = None,
        query_type: str = "default",
    ) -> dict:
        """Search related memories and return structured result."""

        resolved_trace_id = self._normalize_trace_id(trace_id)
        query_id = str(uuid.uuid4())
        raw = self.collection.query(query_texts=[query], n_results=n_results)

        documents = raw.get("documents", [[]])[0] or []
        memory_ids = raw.get("ids", [[]])[0] or []
        distances = raw.get("distances", [[]])[0] or []

        result = SearchResult(
            documents=list(documents),
            memory_ids=list(memory_ids),
            distances=[float(d) for d in distances],
            query_id=query_id,
        )

        self._log_event(
            {
                "event_type": "memory_search",
                "event_ts": self._now_iso(),
                "trace_id": resolved_trace_id,
                "query_id": query_id,
                "query": query,
                "query_type": query_type,
                "top_k": n_results,
                "hits": [
                    {
                        "memory_id": mem_id,
                        "rank": idx + 1,
                        "distance": result.distances[idx]
                        if idx < len(result.distances)
                        else None,
                    }
                    for idx, mem_id in enumerate(result.memory_ids)
                ],
            }
        )
        return result.as_dict()

    def search_texts(
        self,
        query: str,
        n_results: int = 3,
        trace_id: str | None = None,
    ) -> list[str]:
        """Backward-compatible helper returning only text list."""

        result = self.search(query=query, n_results=n_results, trace_id=trace_id)
        return result["documents"]

    def count(self) -> int:
        return self.collection.count()

    def _log_event(self, payload: dict) -> None:
        if not self.config.enable_event_log:
            return
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        event_path = self.config.event_log_dir / f"{day}.jsonl"
        with event_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_trace_id(trace_id: str | None) -> str:
        if trace_id and trace_id.strip():
            return trace_id
        return f"tr_{uuid.uuid4().hex}"
