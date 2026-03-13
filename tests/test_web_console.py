from __future__ import annotations

from base64 import b64encode
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import types

ollama_mod = sys.modules.get("ollama")
if ollama_mod is None or getattr(ollama_mod, "__spec__", None) is None:
    ollama_stub = types.ModuleType("ollama")
    ollama_stub.__spec__ = importlib.machinery.ModuleSpec("ollama", loader=None)

    class _DummyClient:
        def __init__(self, host: str) -> None:
            self.host = host

    ollama_stub.Client = _DummyClient
    sys.modules["ollama"] = ollama_stub

chromadb_mod = sys.modules.get("chromadb")
if chromadb_mod is None or getattr(chromadb_mod, "__spec__", None) is None:
    chromadb_stub = types.ModuleType("chromadb")
    chromadb_utils_stub = types.ModuleType("chromadb.utils")
    embedding_stub = types.ModuleType("chromadb.utils.embedding_functions")
    chromadb_stub.__spec__ = importlib.machinery.ModuleSpec("chromadb", loader=None)
    chromadb_utils_stub.__spec__ = importlib.machinery.ModuleSpec("chromadb.utils", loader=None)
    embedding_stub.__spec__ = importlib.machinery.ModuleSpec("chromadb.utils.embedding_functions", loader=None)

    class _DefaultEmbeddingFunction:
        def __call__(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] for _ in texts]

    embedding_stub.DefaultEmbeddingFunction = _DefaultEmbeddingFunction
    chromadb_utils_stub.embedding_functions = embedding_stub
    chromadb_stub.utils = chromadb_utils_stub

    sys.modules["chromadb"] = chromadb_stub
    sys.modules["chromadb.utils"] = chromadb_utils_stub
    sys.modules["chromadb.utils.embedding_functions"] = embedding_stub

from apps.web_console import server as web_server
from apps.web_console.server import ConsoleState


class _FakeAgent:
    def run_with_trace(self, user_input: str) -> dict[str, object]:
        return {
            "trace_id": "tr_test",
            "user_input": user_input,
            "status": "success",
            "route": "fake",
            "model_name": "fake-model",
            "reply": "done",
            "skill_candidates": [],
            "tool_matches": [],
            "steps": [{"kind": "final", "title": "Final Result", "content": "done", "metadata": {}}],
        }


def test_console_state_returns_trace_payload() -> None:
    state = ConsoleState()
    state._agent = _FakeAgent()  # type: ignore[assignment]

    result = state.run_chat("hello")

    assert result["reply"] == "done"
    assert result["trace_id"] == "tr_test"
    assert result["steps"][0]["kind"] == "final"


def test_console_state_can_save_uploaded_file(tmp_path: Path) -> None:
    original_upload_dir = web_server.UPLOAD_DIR
    web_server.UPLOAD_DIR = tmp_path / "uploads"
    try:
        state = ConsoleState()
        result = state.save_uploaded_file(
            filename="report.txt",
            content_b64=b64encode("hello upload".encode("utf-8")).decode("utf-8"),
        )
    finally:
        web_server.UPLOAD_DIR = original_upload_dir

    assert result["filename"] == "report.txt"
    saved_path = Path(result["saved_path"])
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == "hello upload"
