"""Loop-stall detection for repetitive low-value agent turns."""

from __future__ import annotations

import re
from collections import Counter


class LoopGuard:
    """Track repeated responses and tool cycles to stop obvious dead loops."""

    _WHITESPACE = re.compile(r"\s+")

    def __init__(
        self,
        *,
        repeated_response_limit: int,
        repeated_tool_cycle_limit: int,
    ) -> None:
        self.repeated_response_limit = max(2, repeated_response_limit)
        self.repeated_tool_cycle_limit = max(2, repeated_tool_cycle_limit)
        self._response_counts: Counter[str] = Counter()
        self._tool_cycle_counts: Counter[str] = Counter()

    def record_response(self, response_text: str) -> bool:
        key = self._normalize(response_text)
        if not key:
            return False
        self._response_counts[key] += 1
        return self._response_counts[key] >= self.repeated_response_limit

    def record_tool_cycle(
        self,
        *,
        tool_name: str,
        tool_input: str,
        observation: str,
    ) -> bool:
        key = self._normalize(f"{tool_name}|{tool_input}|{observation}")
        if not key:
            return False
        self._tool_cycle_counts[key] += 1
        return self._tool_cycle_counts[key] >= self.repeated_tool_cycle_limit

    @classmethod
    def _normalize(cls, value: str) -> str:
        return cls._WHITESPACE.sub(" ", value.strip()).lower()
