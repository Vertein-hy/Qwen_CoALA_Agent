#!/usr/bin/env python3
"""Async job gateway for local OpenAI-compatible model servers.

Run this gateway on the same machine as your local model service (e.g. 5070Ti host)
to avoid long-lived FRP connections from IPC.

Client flow:
1) POST /v1/jobs
2) GET /v1/jobs/{job_id} until status=succeeded|failed
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import requests


GATEWAY_HOST = os.getenv("COALA_ASYNC_GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("COALA_ASYNC_GATEWAY_PORT", "8001"))
ALLOW_ORIGIN = os.getenv("COALA_ASYNC_GATEWAY_ALLOW_ORIGIN", "*")

UPSTREAM_API_BASE = os.getenv("COALA_UPSTREAM_API_BASE", "http://127.0.0.1:8000/v1").rstrip("/")
UPSTREAM_MODEL = os.getenv("COALA_UPSTREAM_MODEL", "Qwen3.5-9B-Q4_K_M.gguf")
UPSTREAM_TIMEOUT_S = int(os.getenv("COALA_UPSTREAM_TIMEOUT_S", "600"))
UPSTREAM_API_KEY_ENV = os.getenv("COALA_UPSTREAM_API_KEY_ENV", "COALA_LOCAL_API_KEY")
UPSTREAM_DEFAULT_API_KEY = os.getenv(UPSTREAM_API_KEY_ENV, "local-key").strip()


@dataclass
class JobState:
    id: str
    status: str
    created_at: float
    updated_at: float
    payload: dict[str, Any]
    result: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "job_id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            out["result"] = self.result
        if self.error is not None:
            out["error"] = self.error
        return out


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(self, payload: dict[str, Any]) -> JobState:
        now = time.time()
        job = JobState(
            id=f"job_{uuid.uuid4().hex}",
            status="queued",
            created_at=now,
            updated_at=now,
            payload=payload,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        result: str | None = None,
        error: str | None = None,
    ) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if status is not None:
                job.status = status
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = time.time()
            return job

    def stats(self) -> dict[str, int]:
        with self._lock:
            stats = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
            for job in self._jobs.values():
                stats[job.status] = stats.get(job.status, 0) + 1
            stats["total"] = len(self._jobs)
            return stats


STORE = JobStore()


def _extract_api_key(payload: dict[str, Any], headers: Any) -> str:
    key = str(payload.pop("api_key", "")).strip()
    if key:
        return key
    auth = headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    key = str(headers.get("X-API-Key", "")).strip()
    if key:
        return key
    return UPSTREAM_DEFAULT_API_KEY


def _run_job(job_id: str, payload: dict[str, Any], api_key: str) -> None:
    STORE.update(job_id, status="running")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    chat_payload: dict[str, Any] = {
        "model": str(payload.get("model", UPSTREAM_MODEL)),
        "messages": payload.get("messages", []),
        "temperature": payload.get("temperature", 0.7),
    }
    for key in (
        "top_p",
        "max_tokens",
        "seed",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "response_format",
        "tools",
        "tool_choice",
    ):
        if key in payload:
            chat_payload[key] = payload[key]

    try:
        chat_url = UPSTREAM_API_BASE + "/chat/completions"
        resp = requests.post(chat_url, headers=headers, json=chat_payload, timeout=UPSTREAM_TIMEOUT_S)
        if resp.ok:
            data = resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content", "")
            if isinstance(content, str) and content.strip():
                STORE.update(job_id, status="succeeded", result=content)
                return
    except Exception:
        # Fall through to /completions fallback below.
        pass

    # Fallback for completion-only backends or empty chat content.
    completion_payload = {
        "model": str(payload.get("model", UPSTREAM_MODEL)),
        "prompt": _messages_to_prompt(payload.get("messages", [])),
        "temperature": payload.get("temperature", 0.7),
    }
    if "top_p" in payload:
        completion_payload["top_p"] = payload["top_p"]
    if "max_tokens" in payload:
        completion_payload["max_tokens"] = payload["max_tokens"]

    try:
        completion_url = UPSTREAM_API_BASE + "/completions"
        resp = requests.post(
            completion_url,
            headers=headers,
            json=completion_payload,
            timeout=UPSTREAM_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        text = str(data["choices"][0].get("text", "")).strip()
        if text:
            STORE.update(job_id, status="succeeded", result=text)
            return
        STORE.update(job_id, status="failed", error="Empty result from completions endpoint.")
    except Exception as exc:  # noqa: BLE001
        STORE.update(job_id, status="failed", error=str(exc))


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    lines.append("assistant:")
    return "\n".join(lines)


def _is_jobs_create_path(path: str) -> bool:
    return path in {"/jobs", "/v1/jobs"}


def _extract_job_id(path: str) -> str | None:
    for prefix in ("/jobs/", "/v1/jobs/"):
        if path.startswith(prefix):
            value = path[len(prefix) :].strip("/")
            if value:
                return value
    return None


class AsyncGatewayHandler(BaseHTTPRequestHandler):
    server_version = "CoALALocalAsyncGateway/1.0"

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "upstream_api_base": UPSTREAM_API_BASE,
                    "upstream_model": UPSTREAM_MODEL,
                    "stats": STORE.stats(),
                },
            )
            return

        if self.path in {"/v1/models", "/models"}:
            try:
                r = requests.get(
                    UPSTREAM_API_BASE + "/models",
                    headers={"Authorization": f"Bearer {UPSTREAM_DEFAULT_API_KEY}"},
                    timeout=30,
                )
                r.raise_for_status()
                self._send_json(200, r.json())
            except Exception as exc:  # noqa: BLE001
                self._send_json(502, {"error": "upstream_models_failed", "message": str(exc)})
            return

        job_id = _extract_job_id(self.path)
        if job_id:
            job = STORE.get(job_id)
            if job is None:
                self._send_json(404, {"error": "job_not_found", "job_id": job_id})
                return
            self._send_json(200, job.as_dict())
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if not _is_jobs_create_path(self.path):
            self._send_json(404, {"error": "not_found"})
            return

        payload = self._read_json_body()
        if payload is None:
            return

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            self._send_json(400, {"error": "invalid_input", "message": "messages(list) is required."})
            return

        api_key = _extract_api_key(payload, self.headers)
        job = STORE.create(payload=payload)

        worker = threading.Thread(
            target=_run_job,
            args=(job.id, payload, api_key),
            daemon=True,
            name=f"coala-async-job-{job.id}",
        )
        worker.start()

        self._send_json(
            202,
            {
                "job_id": job.id,
                "status": "queued",
                "status_url": f"/v1/jobs/{job.id}",
            },
        )

    def _read_json_body(self) -> dict[str, Any] | None:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return None

        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return None

        if not isinstance(payload, dict):
            self._send_json(400, {"error": "invalid_json", "message": "JSON object required."})
            return None
        return payload

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[async-gateway] {self.address_string()} {self.command} {self.path} :: {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((GATEWAY_HOST, GATEWAY_PORT), AsyncGatewayHandler)
    print(
        "CoALA local async gateway started at "
        f"http://{GATEWAY_HOST}:{GATEWAY_PORT} "
        f"(upstream={UPSTREAM_API_BASE})"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()

