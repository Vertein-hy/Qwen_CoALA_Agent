"""Minimal web console for chatting and inspection on IPC host.

Design constraints:
- No third-party web framework dependencies.
- Runs in isolated service and does not change FRP/gateway chain.
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from config.settings import load_config
from core.agent import CognitiveAgent
from skills.manager import SkillManager


ROOT_DIR = Path(__file__).resolve().parents[2]
INDEX_HTML_PATH = ROOT_DIR / "apps" / "web_console" / "static" / "index.html"
SKILL_FILE = ROOT_DIR / "skills" / "internalized" / "custom_skills.py"
SKILL_INDEX_FILE = ROOT_DIR / "skills" / "internalized" / "index.json"

HOST = os.getenv("COALA_WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("COALA_WEB_PORT", "7860"))


class ConsoleState:
    """Shared mutable state for the web console process."""

    def __init__(self) -> None:
        self.config = load_config()
        self.skill_manager = SkillManager(
            skill_file=SKILL_FILE,
            index_file=SKILL_INDEX_FILE,
        )
        self._agent: CognitiveAgent | None = None
        self._agent_init_error: str | None = None
        self._lock = threading.Lock()

    def run_chat(self, user_input: str) -> str:
        with self._lock:
            agent = self._ensure_agent()
            return agent.run(user_input)

    def validate_skill(self, code: str) -> dict[str, Any]:
        result = self.skill_manager.validate(code)
        return {
            "is_valid": result.is_valid,
            "function_name": result.function_name,
            "errors": list(result.errors),
            "warnings": list(result.warnings),
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "agent_ready": self._agent is not None,
            "agent_init_error": self._agent_init_error,
            "skill_file": str(SKILL_FILE),
            "skill_index_file": str(SKILL_INDEX_FILE),
            "skill_event_log_dir": str(self.config.skills.event_log_dir),
            "memory_event_log_dir": str(self.config.memory.event_log_dir),
        }

    def _ensure_agent(self) -> CognitiveAgent:
        if self._agent is not None:
            return self._agent
        if self._agent_init_error is not None:
            raise RuntimeError(f"agent initialization failed: {self._agent_init_error}")
        try:
            self._agent = CognitiveAgent(config=self.config, skill_manager=self.skill_manager)
        except Exception as exc:  # noqa: BLE001
            self._agent_init_error = str(exc)
            raise
        return self._agent


STATE = ConsoleState()


def _read_json(path: Path, default: dict | list | None = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default if default is not None else {}


def _tail_jsonl(log_dir: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if not log_dir.exists():
        return []
    files = sorted(log_dir.glob("*.jsonl"))
    if not files:
        return []
    latest = files[-1]
    lines: deque[str] = deque(maxlen=limit)
    with latest.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                lines.append(line.strip())
    rows: list[dict[str, Any]] = []
    for raw in lines:
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            rows.append({"raw": raw})
    return rows


class ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "CoALAWebConsole/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._send_html(INDEX_HTML_PATH.read_text(encoding="utf-8"))
            return

        if path == "/api/health":
            self._send_json(200, STATE.health())
            return

        if path == "/api/skills":
            index_payload = _read_json(SKILL_INDEX_FILE, default={"version": 1, "skills": []})
            source_text = SKILL_FILE.read_text(encoding="utf-8") if SKILL_FILE.exists() else ""
            self._send_json(
                200,
                {
                    "index": index_payload,
                    "source_text": source_text,
                    "enabled_names": STATE.skill_manager.list_skills(),
                },
            )
            return

        if path == "/api/logs":
            kind = (query.get("type", ["skill"])[0] or "skill").strip().lower()
            limit = _safe_int(query.get("limit", ["50"])[0], 50)
            if kind == "memory":
                rows = _tail_jsonl(STATE.config.memory.event_log_dir, limit)
            else:
                rows = _tail_jsonl(STATE.config.skills.event_log_dir, limit)
            self._send_json(200, {"type": kind, "rows": rows})
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/chat":
            payload = self._read_json_body()
            if payload is None:
                return
            user_input = str(payload.get("message", "")).strip()
            if not user_input:
                self._send_json(400, {"error": "message is required"})
                return
            try:
                reply = STATE.run_chat(user_input)
            except Exception as exc:  # noqa: BLE001
                self._send_json(500, {"error": str(exc)})
                return
            self._send_json(200, {"reply": reply})
            return

        if self.path == "/api/validate-skill":
            payload = self._read_json_body()
            if payload is None:
                return
            code = str(payload.get("code", ""))
            self._send_json(200, STATE.validate_skill(code))
            return

        self._send_json(404, {"error": "not_found"})

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def _read_json_body(self) -> dict[str, Any] | None:
        length = _safe_int(self.headers.get("Content-Length", "0"), 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "invalid_json_object"})
            return None
        return payload

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[web-console] {self.command} {self.path} :: {fmt % args}")


def _safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ConsoleHandler)
    print(f"CoALA web console started at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
