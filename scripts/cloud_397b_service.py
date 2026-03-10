#!/usr/bin/env python3
"""Minimal HTTP gateway for Qwen 397B (OpenAI-compatible remote API).

Usage:
  python scripts/cloud_397b_service.py

Endpoints:
  GET  /health
  POST /v1/chat/completions
  POST /chat

The caller can pass API key in one of:
  1) JSON body: {"api_key": "..."}
  2) Header: Authorization: Bearer ...
  3) Header: X-API-Key: ...
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import requests


REMOTE_API_BASE = os.getenv(
    "COALA_REMOTE_API_BASE",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
).rstrip("/")
DEFAULT_MODEL = os.getenv("COALA_REMOTE_MODEL", "qwen3.5-397b-a17b")
REQUEST_TIMEOUT_S = int(os.getenv("COALA_REMOTE_TIMEOUT_S", "120"))
REMOTE_API_KEY_ENV = os.getenv("COALA_REMOTE_API_KEY_ENV", "QWEN_API_KEY")
DEFAULT_API_KEY = os.getenv(REMOTE_API_KEY_ENV, "").strip()

SERVICE_HOST = os.getenv("COALA_SERVICE_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("COALA_SERVICE_PORT", "18080"))
ALLOW_ORIGIN = os.getenv("COALA_SERVICE_ALLOW_ORIGIN", "*")


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

    return DEFAULT_API_KEY


def _normalize_messages(payload: dict[str, Any]) -> list[dict[str, str]] | None:
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        return messages

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return [{"role": "user", "content": message.strip()}]

    return None


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "CoALACloudGateway/1.0"

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
                    "remote_api_base": REMOTE_API_BASE,
                    "default_model": DEFAULT_MODEL,
                    "default_api_key_env": REMOTE_API_KEY_ENV,
                    "has_default_api_key": bool(DEFAULT_API_KEY),
                },
            )
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/v1/chat/completions", "/chat"}:
            self._send_json(404, {"error": "not_found"})
            return

        payload = self._read_json_body()
        if payload is None:
            return

        api_key = _extract_api_key(payload, self.headers)
        if not api_key:
            self._send_json(
                400,
                {
                    "error": "missing_api_key",
                    "message": (
                        "Provide api_key in body/header, "
                        f"or set default key in env var {REMOTE_API_KEY_ENV}."
                    ),
                },
            )
            return

        messages = _normalize_messages(payload)
        if not messages:
            self._send_json(
                400,
                {"error": "invalid_input", "message": "Provide 'messages' or 'message'."},
            )
            return

        upstream_payload = {
            "model": str(payload.get("model", DEFAULT_MODEL)),
            "messages": messages,
        }

        # Forward common generation params if present.
        for key in (
            "temperature",
            "top_p",
            "max_tokens",
            "seed",
            "stream",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "response_format",
            "tools",
            "tool_choice",
        ):
            if key in payload:
                upstream_payload[key] = payload[key]

        try:
            upstream_resp = requests.post(
                REMOTE_API_BASE + "/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=upstream_payload,
                timeout=REQUEST_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            self._send_json(502, {"error": "upstream_unreachable", "message": str(exc)})
            return

        try:
            upstream_json = upstream_resp.json()
        except ValueError:
            self._send_json(
                502,
                {
                    "error": "upstream_invalid_response",
                    "status_code": upstream_resp.status_code,
                    "body": upstream_resp.text[:1000],
                },
            )
            return

        self._send_json(upstream_resp.status_code, upstream_json)

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
        # Keep logs concise and machine-readable.
        print(f"[gateway] {self.address_string()} {self.command} {self.path} :: {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((SERVICE_HOST, SERVICE_PORT), GatewayHandler)
    print(
        "CoALA cloud gateway started at "
        f"http://{SERVICE_HOST}:{SERVICE_PORT} -> {REMOTE_API_BASE}/chat/completions"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
