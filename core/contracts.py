"""Core abstraction contracts used across the project.

These interfaces keep modules decoupled and make future provider replacement
or feature extension possible without changing call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


Message = dict[str, str]


@dataclass(frozen=True)
class ChatResult:
    """Structured LLM output with trace metadata."""

    content: str
    model_name: str
    route: str


@dataclass(frozen=True)
class ModelCapabilities:
    """Feature flags describing what a provider can honor reliably."""

    supports_top_p: bool = True
    supports_top_k: bool = False
    supports_max_tokens: bool = True
    supports_seed: bool = False
    supports_json_schema: bool = False
    supports_tool_calls: bool = False


@dataclass(frozen=True)
class GenerationOptions:
    """Normalized generation controls used across providers."""

    temperature: float = 0.7
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    seed: int | None = None


class ChatModel(Protocol):
    """Minimal model interface for chat completion providers."""

    @property
    def model_name(self) -> str:
        ...

    def generate(self, messages: list[Message], temperature: float = 0.7) -> str:
        ...


class ModelRouter(Protocol):
    """Policy interface that selects which model should handle a request."""

    def select_model(self, user_input: str) -> ChatModel:
        ...

    def describe_last_decision(self) -> str:
        ...


class LongTermMemory(Protocol):
    """Long-term memory behavior expected by the agent."""

    def add(
        self,
        text: str,
        metadata: dict | None = None,
        trace_id: str | None = None,
        write_reason: str | None = None,
        source: str = "self_generated",
        score_snapshot: dict | None = None,
    ) -> str:
        ...

    def search(
        self,
        query: str,
        n_results: int = 3,
        trace_id: str | None = None,
        query_type: str = "default",
    ) -> dict:
        ...


class ToolExecutor(Protocol):
    """Tool calling interface expected by the agent loop."""

    def execute(self, tool_name: str, tool_input: str) -> str:
        ...

    def get_tool_desc(self) -> str:
        ...
