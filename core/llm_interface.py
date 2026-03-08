"""Unified LLM facade.

Keeps backward-compatible `chat()` while supporting:
- local small model
- remote large model
- auto routing by request complexity
"""

from __future__ import annotations

from config.settings import AppConfig, LocalModelConfig, load_config
from core.contracts import (
    ChatModel,
    ChatResult,
    GenerationOptions,
    Message,
    ModelCapabilities,
)
from core.llm_providers import LocalOllamaChatModel, OpenAICompatChatModel
from core.model_router import RuleBasedModelRouter


class LLMInterface:
    """Single entry point for all model invocations."""

    def __init__(self, config: AppConfig | None = None):
        self.config = config or load_config()

        self.small_model = self._build_local_provider(self.config.local_model)
        self.large_model = OpenAICompatChatModel(
            model=self.config.remote_model.model,
            api_base=self.config.remote_model.api_base,
            api_key_env=self.config.remote_model.api_key_env,
            require_api_key=True,
            timeout_s=self.config.remote_model.timeout_s,
        )
        self.router = RuleBasedModelRouter(
            small_model=self.small_model,
            large_model=self.large_model,
            complexity_threshold=self.config.routing.complexity_threshold,
            force_large_keywords=self.config.routing.force_large_keywords,
        )

    def chat_with_meta(
        self,
        messages: list[Message],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        """Generate response and return route metadata."""

        temp = (
            temperature
            if temperature is not None
            else self.config.agent.default_temperature
        )
        user_input = self._last_user_message(messages)

        if route_hint == "small":
            provider = self.small_model
            route = "forced_small"
        elif route_hint == "large":
            provider = self.large_model
            route = "forced_large"
        else:
            provider = self.router.select_model(user_input)
            route = self.router.describe_last_decision()

        requested_options = GenerationOptions(
            temperature=temp,
            top_p=self.config.agent.default_top_p,
            top_k=self.config.agent.default_top_k,
            max_tokens=self.config.agent.default_max_tokens,
            seed=self.config.agent.default_seed,
        )
        applied_options, dropped_fields = self._negotiate_generation_options(
            provider=provider,
            requested=requested_options,
        )

        try:
            content = self._generate_with_options(
                provider=provider,
                messages=messages,
                options=applied_options,
            )
            route = self._merge_route_metadata(route, dropped_fields)
            return ChatResult(
                content=content,
                model_name=provider.model_name,
                route=route,
            )
        except Exception as first_error:
            if provider is self.large_model:
                fallback = self.small_model
                fallback_options, fallback_dropped = self._negotiate_generation_options(
                    provider=fallback,
                    requested=requested_options,
                )
                content = self._generate_with_options(
                    provider=fallback,
                    messages=messages,
                    options=fallback_options,
                )
                fallback_route = f"fallback_to_small:{type(first_error).__name__}"
                fallback_route = self._merge_route_metadata(
                    fallback_route,
                    fallback_dropped,
                )
                return ChatResult(
                    content=content,
                    model_name=fallback.model_name,
                    route=fallback_route,
                )
            raise RuntimeError(f"LLM generation failed: {first_error}") from first_error

    def chat(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        route_hint: str = "auto",
    ) -> str:
        """Backward-compatible chat API returning plain text only."""

        result = self.chat_with_meta(
            messages=messages,
            temperature=temperature,
            route_hint=route_hint,
        )
        return result.content

    @staticmethod
    def _last_user_message(messages: list[Message]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    @staticmethod
    def _build_local_provider(local_cfg: LocalModelConfig) -> ChatModel:
        provider = local_cfg.provider.strip().lower()
        if provider in {"openai", "openai_compat", "vllm", "sglang"}:
            return OpenAICompatChatModel(
                model=local_cfg.name,
                api_base=local_cfg.api_base,
                api_key_env=local_cfg.api_key_env,
                require_api_key=local_cfg.require_api_key,
                timeout_s=local_cfg.timeout_s,
                supports_top_k=local_cfg.supports_top_k,
                supports_seed=True,
                supports_json_schema=True,
                supports_tool_calls=True,
            )
        if provider == "ollama":
            return LocalOllamaChatModel(
                name=local_cfg.name,
                host=local_cfg.host,
                timeout_s=local_cfg.timeout_s,
                num_ctx=local_cfg.num_ctx,
            )
        raise ValueError(
            "Unsupported local provider. "
            "Expected one of: openai_compat, vllm, sglang, ollama."
        )

    @staticmethod
    def _provider_capabilities(provider: ChatModel) -> ModelCapabilities:
        caps = getattr(provider, "capabilities", None)
        if isinstance(caps, ModelCapabilities):
            return caps
        return ModelCapabilities()

    def _negotiate_generation_options(
        self,
        provider: ChatModel,
        requested: GenerationOptions,
    ) -> tuple[GenerationOptions, list[str]]:
        caps = self._provider_capabilities(provider)
        dropped: list[str] = []

        top_p = requested.top_p
        if top_p is not None and not caps.supports_top_p:
            top_p = None
            dropped.append("top_p")

        top_k = requested.top_k
        if top_k is not None and not caps.supports_top_k:
            top_k = None
            dropped.append("top_k")

        max_tokens = requested.max_tokens
        if max_tokens is not None and not caps.supports_max_tokens:
            max_tokens = None
            dropped.append("max_tokens")

        seed = requested.seed
        if seed is not None and not caps.supports_seed:
            seed = None
            dropped.append("seed")

        return (
            GenerationOptions(
                temperature=requested.temperature,
                top_p=top_p,
                top_k=top_k,
                max_tokens=max_tokens,
                seed=seed,
            ),
            dropped,
        )

    @staticmethod
    def _generate_with_options(
        provider: ChatModel,
        messages: list[Message],
        options: GenerationOptions,
    ) -> str:
        generator = getattr(provider, "generate_with_options", None)
        if callable(generator):
            return generator(messages=messages, options=options)
        return provider.generate(messages=messages, temperature=options.temperature)

    @staticmethod
    def _merge_route_metadata(route: str, dropped_fields: list[str]) -> str:
        if not dropped_fields:
            return route
        fields = ",".join(sorted(set(dropped_fields)))
        return f"{route}|degraded={fields}"
