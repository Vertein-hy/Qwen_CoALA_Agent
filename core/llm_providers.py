"""LLM provider implementations.

This module keeps providers lightweight and focused:
- `OpenAICompatChatModel`: works for both remote APIs and local vLLM/SGLang.
- `LocalOllamaChatModel`: optional fallback provider.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from core.contracts import GenerationOptions, Message, ModelCapabilities


@dataclass
class LocalOllamaChatModel:
    """Optional Ollama-based local model provider."""

    name: str
    host: str
    timeout_s: int = 120
    num_ctx: int = 8192
    capabilities: ModelCapabilities = field(
        default_factory=lambda: ModelCapabilities(
            supports_top_p=True,
            supports_top_k=True,
            supports_max_tokens=True,
            supports_seed=True,
            supports_json_schema=False,
            supports_tool_calls=False,
        )
    )

    def __post_init__(self) -> None:
        try:
            import ollama  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Ollama provider selected but package 'ollama' is not installed."
            ) from exc
        self._client = ollama.Client(host=self.host)

    @property
    def model_name(self) -> str:
        return self.name

    def generate(self, messages: list[Message], temperature: float = 0.7) -> str:
        return self.generate_with_options(
            messages=messages,
            options=GenerationOptions(temperature=temperature),
        )

    def generate_with_options(
        self,
        messages: list[Message],
        options: GenerationOptions,
    ) -> str:
        payload_options: dict[str, Any] = {
            "temperature": options.temperature,
            "num_ctx": self.num_ctx,
        }
        if options.top_p is not None:
            payload_options["top_p"] = options.top_p
        if options.top_k is not None:
            payload_options["top_k"] = options.top_k
        if options.max_tokens is not None:
            payload_options["num_predict"] = options.max_tokens
        if options.seed is not None:
            payload_options["seed"] = options.seed

        response = self._client.chat(
            model=self.name,
            messages=messages,
            stream=False,
            options=payload_options,
        )
        return response["message"]["content"]


@dataclass
class OpenAICompatChatModel:
    """OpenAI-compatible HTTP provider for remote or local endpoints."""

    model: str
    api_base: str
    api_key_env: str = "QWEN_API_KEY"
    require_api_key: bool = True
    timeout_s: int = 90
    supports_top_k: bool = False
    supports_seed: bool = True
    supports_json_schema: bool = True
    supports_tool_calls: bool = True
    async_enabled: bool = False
    async_submit_path: str = "/jobs"
    async_status_path_template: str = "/jobs/{job_id}"
    async_poll_interval_s: float = 1.0
    async_timeout_s: int = 600
    capabilities: ModelCapabilities = field(init=False)

    def __post_init__(self) -> None:
        self.capabilities = ModelCapabilities(
            supports_top_p=True,
            supports_top_k=self.supports_top_k,
            supports_max_tokens=True,
            supports_seed=self.supports_seed,
            supports_json_schema=self.supports_json_schema,
            supports_tool_calls=self.supports_tool_calls,
        )

    @property
    def model_name(self) -> str:
        return self.model

    def _api_key(self) -> str:
        key = os.getenv(self.api_key_env, "").strip()
        if key:
            return key
        if self.require_api_key:
            raise RuntimeError(
                f"Missing API key. Please set env var: {self.api_key_env}"
            )
        # Many local OpenAI-compatible servers accept any non-empty key.
        return "local-key"

    def _build_payload(
        self,
        messages: list[Message],
        options: GenerationOptions,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": options.temperature,
        }
        if options.top_p is not None:
            payload["top_p"] = options.top_p
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if options.seed is not None and self.capabilities.supports_seed:
            payload["seed"] = options.seed
        if options.top_k is not None and self.capabilities.supports_top_k:
            payload["top_k"] = options.top_k
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }

    def generate(self, messages: list[Message], temperature: float = 0.7) -> str:
        return self.generate_with_options(
            messages=messages,
            options=GenerationOptions(temperature=temperature),
        )

    def generate_with_options(
        self,
        messages: list[Message],
        options: GenerationOptions,
    ) -> str:
        if self.async_enabled:
            return self._generate_via_async_jobs(messages=messages, options=options)

        chat_url = self.api_base.rstrip("/") + "/chat/completions"
        chat_payload = self._build_payload(messages=messages, options=options)
        chat_error: Exception | None = None
        try:
            response = requests.post(
                chat_url,
                headers=self._headers(),
                json=chat_payload,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            chat_error = exc
        else:
            if response.ok:
                data = response.json()
                try:
                    message = data["choices"][0]["message"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise RuntimeError(
                        f"Unexpected response format from {chat_url}: {data}"
                    ) from exc

                content = message.get("content", "")
                if isinstance(content, str) and content.strip():
                    return content

                # Some backends return reasoning-only chat responses.
                # Fall back to /completions to get deterministic plain text.
                chat_error = RuntimeError(
                    f"Empty content from {chat_url}, trying /completions fallback."
                )
            else:
                chat_error = RuntimeError(
                    f"{chat_url} returned status={response.status_code}"
                )

        # Some local OpenAI-compatible servers only expose /v1/completions.
        completion_url = self.api_base.rstrip("/") + "/completions"
        completion_payload = {
            "model": self.model,
            "prompt": self._messages_to_prompt(messages),
            "temperature": options.temperature,
        }
        if options.max_tokens is not None:
            completion_payload["max_tokens"] = options.max_tokens
        if options.top_p is not None:
            completion_payload["top_p"] = options.top_p

        try:
            fallback = requests.post(
                completion_url,
                headers=self._headers(),
                json=completion_payload,
                timeout=self.timeout_s,
            )
            fallback.raise_for_status()
            data = fallback.json()
            try:
                return data["choices"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Unexpected response format from {completion_url}: {data}"
                ) from exc
        except Exception as exc:  # noqa: BLE001
            if chat_error is not None:
                raise RuntimeError(
                    "OpenAI-compatible call failed for both endpoints. "
                    f"chat_error={chat_error}; completion_error={exc}"
                ) from exc
            raise

    def _generate_via_async_jobs(
        self,
        messages: list[Message],
        options: GenerationOptions,
    ) -> str:
        submit_url = self._join_url(self.async_submit_path)
        payload = self._build_payload(messages=messages, options=options)
        submit = requests.post(
            submit_url,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_s,
        )
        submit.raise_for_status()

        submit_data = submit.json()
        job_id = str(
            submit_data.get("job_id")
            or submit_data.get("id")
            or ""
        ).strip()
        if not job_id:
            raise RuntimeError(
                f"Async gateway did not return job_id. response={submit_data}"
            )

        status_path = self.async_status_path_template.format(job_id=job_id)
        status_url = self._join_url(status_path)
        deadline = time.time() + max(1, int(self.async_timeout_s))

        while time.time() < deadline:
            status_resp = requests.get(
                status_url,
                headers=self._headers(),
                timeout=self.timeout_s,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = str(status_data.get("status", "")).lower()

            if status in {"succeeded", "done", "completed", "success"}:
                result = status_data.get("result")
                if isinstance(result, str) and result.strip():
                    return result
                if isinstance(result, dict):
                    text = result.get("content") or result.get("text")
                    if isinstance(text, str) and text.strip():
                        return text
                # Be tolerant with different response shapes.
                text = status_data.get("content") or status_data.get("text")
                if isinstance(text, str) and text.strip():
                    return text
                raise RuntimeError(
                    f"Async job succeeded but no text payload found. job_id={job_id}"
                )

            if status in {"failed", "error", "cancelled"}:
                error = status_data.get("error", "unknown_error")
                raise RuntimeError(f"Async job failed. job_id={job_id}; error={error}")

            time.sleep(max(0.05, float(self.async_poll_interval_s)))

        raise RuntimeError(f"Async job timeout. job_id={job_id}; timeout_s={self.async_timeout_s}")

    def _join_url(self, path: str) -> str:
        base = self.api_base.rstrip("/")
        if not path:
            return base
        if path.startswith("/"):
            return base + path
        return base + "/" + path

    @staticmethod
    def _messages_to_prompt(messages: list[Message]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        lines.append("assistant:")
        return "\n".join(lines)
