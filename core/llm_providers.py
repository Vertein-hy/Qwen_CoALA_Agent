"""LLM provider implementations.

This module keeps providers lightweight and focused:
- `OpenAICompatChatModel`: works for both remote APIs and local vLLM/SGLang.
- `LocalOllamaChatModel`: optional fallback provider.
"""

from __future__ import annotations

import os
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
        chat_url = self.api_base.rstrip("/") + "/chat/completions"
        chat_payload = self._build_payload(messages=messages, options=options)
        response = requests.post(
            chat_url,
            headers=self._headers(),
            json=chat_payload,
            timeout=self.timeout_s,
        )
        if response.ok:
            data = response.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Unexpected response format from {chat_url}: {data}"
                ) from exc

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

    @staticmethod
    def _messages_to_prompt(messages: list[Message]) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        lines.append("assistant:")
        return "\n".join(lines)
