"""Rule-based routing between local and remote models."""

from __future__ import annotations

from dataclasses import dataclass

from core.contracts import ChatModel


@dataclass
class RuleBasedModelRouter:
    """Simple and explainable model router.

    This implementation is intentionally deterministic to simplify debugging.
    """

    small_model: ChatModel
    large_model: ChatModel
    complexity_threshold: int
    force_large_keywords: tuple[str, ...]

    def __post_init__(self) -> None:
        self._last_reason = "default_small"

    def _estimate_complexity(self, user_input: str) -> int:
        score = 0
        text = user_input.strip()

        if len(text) > 120:
            score += 1
        if len(text) > 260:
            score += 1

        multi_step_hints = ["并且", "然后", "同时", "步骤", "分析", "设计", "重构"]
        if any(token in text for token in multi_step_hints):
            score += 1

        if any(ch in text for ch in ["`", "{", "}", "def ", "class "]):
            score += 1

        return score

    def select_model(self, user_input: str) -> ChatModel:
        text = user_input.strip()

        if text.lower().startswith("[small]"):
            self._last_reason = "forced_small"
            return self.small_model

        if text.lower().startswith("[large]"):
            self._last_reason = "forced_large"
            return self.large_model

        if any(keyword in text for keyword in self.force_large_keywords):
            self._last_reason = "keyword_large"
            return self.large_model

        complexity = self._estimate_complexity(text)
        if complexity >= self.complexity_threshold:
            self._last_reason = f"complexity_large:{complexity}"
            return self.large_model

        self._last_reason = f"complexity_small:{complexity}"
        return self.small_model

    def describe_last_decision(self) -> str:
        return self._last_reason
