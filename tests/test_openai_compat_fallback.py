from __future__ import annotations

import requests

from core.contracts import GenerationOptions
from core.llm_providers import OpenAICompatChatModel


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"status={self.status_code}")


def test_openai_compat_falls_back_to_completions(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_post(url: str, headers: dict, json: dict, timeout: int):  # type: ignore[override]
        del headers, timeout
        calls.append(url)
        if url.endswith("/chat/completions"):
            return _Resp(500, {"error": {"message": "parse error"}})
        assert json.get("prompt", "").endswith("assistant:")
        return _Resp(200, {"choices": [{"text": "fallback-ok"}]})

    monkeypatch.setattr("core.llm_providers.requests.post", _fake_post)

    model = OpenAICompatChatModel(
        model="qwen-local-gguf",
        api_base="http://127.0.0.1:8000/v1",
        require_api_key=False,
    )
    out = model.generate_with_options(
        messages=[{"role": "user", "content": "hi"}],
        options=GenerationOptions(temperature=0.1, max_tokens=16),
    )

    assert out == "fallback-ok"
    assert calls[0].endswith("/chat/completions")
    assert calls[1].endswith("/completions")


def test_openai_compat_falls_back_when_chat_connection_errors(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_post(url: str, headers: dict, json: dict, timeout: int):  # type: ignore[override]
        del headers, timeout
        calls.append(url)
        if url.endswith("/chat/completions"):
            raise requests.ConnectionError("connection reset by peer")
        assert json.get("prompt", "").endswith("assistant:")
        return _Resp(200, {"choices": [{"text": "fallback-after-conn-error"}]})

    monkeypatch.setattr("core.llm_providers.requests.post", _fake_post)

    model = OpenAICompatChatModel(
        model="qwen-local-gguf",
        api_base="http://127.0.0.1:8000/v1",
        require_api_key=False,
    )
    out = model.generate_with_options(
        messages=[{"role": "user", "content": "hi"}],
        options=GenerationOptions(temperature=0.1, max_tokens=16),
    )

    assert out == "fallback-after-conn-error"
    assert calls[0].endswith("/chat/completions")
    assert calls[1].endswith("/completions")


def test_openai_compat_async_job_mode(monkeypatch) -> None:
    post_calls: list[str] = []
    get_calls: list[str] = []

    def _fake_post(url: str, headers: dict, json: dict, timeout: int):  # type: ignore[override]
        del headers, timeout
        post_calls.append(url)
        assert json["messages"][0]["content"] == "hi"
        return _Resp(202, {"job_id": "job_123", "status": "queued"})

    states = [
        _Resp(200, {"job_id": "job_123", "status": "running"}),
        _Resp(200, {"job_id": "job_123", "status": "succeeded", "result": "async-ok"}),
    ]

    def _fake_get(url: str, headers: dict, timeout: int):  # type: ignore[override]
        del headers, timeout
        get_calls.append(url)
        return states.pop(0)

    monkeypatch.setattr("core.llm_providers.requests.post", _fake_post)
    monkeypatch.setattr("core.llm_providers.requests.get", _fake_get)

    model = OpenAICompatChatModel(
        model="qwen-local-gguf",
        api_base="http://127.0.0.1:18081/v1",
        require_api_key=False,
        async_enabled=True,
        async_submit_path="/jobs",
        async_status_path_template="/jobs/{job_id}",
        async_poll_interval_s=0.01,
        async_timeout_s=5,
    )
    out = model.generate_with_options(
        messages=[{"role": "user", "content": "hi"}],
        options=GenerationOptions(temperature=0.1, max_tokens=16),
    )

    assert out == "async-ok"
    assert post_calls[0].endswith("/v1/jobs")
    assert get_calls[0].endswith("/v1/jobs/job_123")
