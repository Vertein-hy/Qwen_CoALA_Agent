from __future__ import annotations

from config.settings import AgentConfig, AppConfig, LocalModelConfig
from core.contracts import GenerationOptions, ModelCapabilities
from core.llm_interface import LLMInterface
from core.llm_providers import OpenAICompatChatModel


class _RecordingProvider:
    def __init__(self, capabilities: ModelCapabilities):
        self.capabilities = capabilities
        self.last_options: GenerationOptions | None = None
        self._model_name = "recording-local"

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        return "legacy-path"

    def generate_with_options(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions,
    ) -> str:
        self.last_options = options
        return "ok"


def _build_config(
    default_top_p: float = 0.8,
    default_top_k: int | None = None,
    default_max_tokens: int = 1024,
    default_seed: int | None = None,
) -> AppConfig:
    agent = AgentConfig(
        max_steps=5,
        memory_top_k=3,
        default_temperature=0.7,
        default_top_p=default_top_p,
        default_top_k=default_top_k,
        default_max_tokens=default_max_tokens,
        default_seed=default_seed,
    )
    local = LocalModelConfig(
        provider="openai_compat",
        name="Qwen/Qwen3.5-9B-Instruct",
        api_base="http://127.0.0.1:8000/v1",
        api_key_env="COALA_LOCAL_API_KEY",
        require_api_key=False,
    )
    return AppConfig(local_model=local, agent=agent)


def test_local_provider_defaults_to_openai_compat() -> None:
    llm = LLMInterface(config=_build_config())
    assert isinstance(llm.small_model, OpenAICompatChatModel)
    assert llm.small_model.model_name == "Qwen/Qwen3.5-9B-Instruct"


def test_negotiate_generation_options_drops_unsupported_fields() -> None:
    llm = LLMInterface(config=_build_config())
    provider = _RecordingProvider(
        capabilities=ModelCapabilities(
            supports_top_p=True,
            supports_top_k=False,
            supports_max_tokens=False,
            supports_seed=False,
        )
    )
    requested = GenerationOptions(
        temperature=0.3,
        top_p=0.9,
        top_k=40,
        max_tokens=512,
        seed=7,
    )

    applied, dropped = llm._negotiate_generation_options(provider, requested)

    assert applied.top_p == 0.9
    assert applied.top_k is None
    assert applied.max_tokens is None
    assert applied.seed is None
    assert set(dropped) == {"top_k", "max_tokens", "seed"}


def test_chat_with_meta_reports_degraded_fields() -> None:
    llm = LLMInterface(
        config=_build_config(default_top_k=32, default_seed=1234),
    )
    provider = _RecordingProvider(
        capabilities=ModelCapabilities(
            supports_top_p=True,
            supports_top_k=False,
            supports_max_tokens=True,
            supports_seed=False,
        )
    )
    llm.small_model = provider
    llm.router.small_model = provider

    result = llm.chat_with_meta(
        messages=[{"role": "user", "content": "hello"}],
        route_hint="small",
    )

    assert result.content == "ok"
    assert result.route == "forced_small|degraded=seed,top_k"
    assert provider.last_options is not None
    assert provider.last_options.top_k is None
    assert provider.last_options.seed is None
