"""Application settings and typed configuration objects.

This module keeps backward compatibility with old constants while exposing a
structured config API for new code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    """Load .env key-value pairs into process env if not already set."""

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class LocalModelConfig:
    """Configuration for the local small model backend."""

    provider: str = "openai_compat"
    name: str = "Qwen/Qwen3.5-9B-Instruct"
    host: str = "http://127.0.0.1:11434"
    api_base: str = "http://127.0.0.1:8000/v1"
    api_key_env: str = "COALA_LOCAL_API_KEY"
    require_api_key: bool = False
    timeout_s: int = 120
    async_enabled: bool = False
    async_submit_path: str = "/jobs"
    async_status_path_template: str = "/jobs/{job_id}"
    async_poll_interval_s: float = 1.0
    async_timeout_s: int = 600
    num_ctx: int = 8192
    model_profile: str = "qwen3.5-9b"
    supports_top_k: bool = False


@dataclass(frozen=True)
class RemoteModelConfig:
    """Configuration for the remote large model backend.

    The remote endpoint is expected to be OpenAI-compatible and supports
    /chat/completions.
    """

    model: str = "qwen3.5-397b-a17b"
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key_env: str = "QWEN_API_KEY"
    timeout_s: int = 90


@dataclass(frozen=True)
class RoutingConfig:
    """Routing policy between small and large model."""

    complexity_threshold: int = 3
    force_large_keywords: tuple[str, ...] = (
        "架构",
        "重构",
        "优化方案",
        "多步骤",
        "推导",
        "proof",
        "benchmark",
        "safety",
    )


@dataclass(frozen=True)
class MemoryConfig:
    """Configuration for long-term memory and event logs."""

    vector_db_path: Path = BASE_DIR / "data" / "chroma_db"
    enable_event_log: bool = True
    event_log_dir: Path = BASE_DIR / "data" / "logs" / "memory_events"


@dataclass(frozen=True)
class AgentConfig:
    """Runtime behavior configuration for the agent loop."""

    max_steps: int = 5
    memory_top_k: int = 3
    response_language: str = "zh-CN"
    default_temperature: float = 0.7
    default_top_p: float = 0.8
    default_top_k: int | None = None
    default_max_tokens: int = 1024
    default_seed: int | None = None


@dataclass(frozen=True)
class AppConfig:
    """Top-level app configuration container."""

    local_model: LocalModelConfig = field(default_factory=LocalModelConfig)
    remote_model: RemoteModelConfig = field(default_factory=RemoteModelConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)


def _bool_from_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int_from_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return int(value)


def load_config() -> AppConfig:
    """Load config from environment with safe defaults.

    Existing deployments can override any field by setting env vars.
    """
    _load_dotenv(ENV_FILE)

    local = LocalModelConfig(
        provider=os.getenv("COALA_LOCAL_PROVIDER", "openai_compat"),
        name=os.getenv("COALA_LOCAL_MODEL", "Qwen/Qwen3.5-9B-Instruct"),
        host=os.getenv("COALA_OLLAMA_HOST", "http://127.0.0.1:11434"),
        api_base=os.getenv("COALA_LOCAL_API_BASE", "http://127.0.0.1:8000/v1"),
        api_key_env=os.getenv("COALA_LOCAL_API_KEY_ENV", "COALA_LOCAL_API_KEY"),
        require_api_key=_bool_from_env("COALA_LOCAL_REQUIRE_API_KEY", False),
        timeout_s=int(os.getenv("COALA_LOCAL_TIMEOUT_S", "120")),
        async_enabled=_bool_from_env("COALA_LOCAL_ASYNC_ENABLED", False),
        async_submit_path=os.getenv("COALA_LOCAL_ASYNC_SUBMIT_PATH", "/jobs"),
        async_status_path_template=os.getenv(
            "COALA_LOCAL_ASYNC_STATUS_PATH_TEMPLATE",
            "/jobs/{job_id}",
        ),
        async_poll_interval_s=float(
            os.getenv("COALA_LOCAL_ASYNC_POLL_INTERVAL_S", "1.0")
        ),
        async_timeout_s=int(os.getenv("COALA_LOCAL_ASYNC_TIMEOUT_S", "600")),
        num_ctx=int(os.getenv("COALA_LOCAL_NUM_CTX", "8192")),
        model_profile=os.getenv("COALA_LOCAL_MODEL_PROFILE", "qwen3.5-9b"),
        supports_top_k=_bool_from_env("COALA_LOCAL_SUPPORTS_TOP_K", False),
    )

    remote = RemoteModelConfig(
        model=os.getenv("COALA_REMOTE_MODEL", "qwen3.5-397b-a17b"),
        api_base=os.getenv(
            "COALA_REMOTE_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        api_key_env=os.getenv("COALA_REMOTE_API_KEY_ENV", "QWEN_API_KEY"),
        timeout_s=int(os.getenv("COALA_REMOTE_TIMEOUT_S", "90")),
    )

    routing = RoutingConfig(
        complexity_threshold=int(os.getenv("COALA_ROUTE_COMPLEXITY_THRESHOLD", "3")),
        force_large_keywords=tuple(
            x.strip()
            for x in os.getenv(
                "COALA_FORCE_LARGE_KEYWORDS",
                "架构,重构,优化方案,多步骤,推导,proof,benchmark,safety",
            ).split(",")
            if x.strip()
        ),
    )

    memory = MemoryConfig(
        vector_db_path=Path(
            os.getenv("COALA_VECTOR_DB_PATH", str(BASE_DIR / "data" / "chroma_db"))
        ),
        enable_event_log=_bool_from_env("COALA_MEMORY_EVENT_LOG", True),
        event_log_dir=Path(
            os.getenv(
                "COALA_MEMORY_EVENT_LOG_DIR",
                str(BASE_DIR / "data" / "logs" / "memory_events"),
            )
        ),
    )

    agent = AgentConfig(
        max_steps=int(os.getenv("COALA_AGENT_MAX_STEPS", "5")),
        memory_top_k=int(os.getenv("COALA_AGENT_MEMORY_TOP_K", "3")),
        response_language=os.getenv("COALA_AGENT_RESPONSE_LANGUAGE", "zh-CN"),
        default_temperature=float(os.getenv("COALA_AGENT_TEMPERATURE", "0.7")),
        default_top_p=float(os.getenv("COALA_AGENT_TOP_P", "0.8")),
        default_top_k=_optional_int_from_env("COALA_AGENT_TOP_K"),
        default_max_tokens=int(os.getenv("COALA_AGENT_MAX_TOKENS", "1024")),
        default_seed=_optional_int_from_env("COALA_AGENT_SEED"),
    )

    return AppConfig(
        local_model=local,
        remote_model=remote,
        routing=routing,
        memory=memory,
        agent=agent,
    )


# ---------------------------------------------------------------------------
# Backward compatible constants (legacy imports still work)
# ---------------------------------------------------------------------------
_loaded = load_config()
OLLAMA_MODEL_NAME = _loaded.local_model.name
OLLAMA_HOST = _loaded.local_model.host
VECTOR_DB_PATH = str(_loaded.memory.vector_db_path)
