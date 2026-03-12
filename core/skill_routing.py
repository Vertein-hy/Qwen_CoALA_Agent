"""Deterministic skill-routing helpers for small-model execution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills.selector import SkillCandidate


@dataclass(frozen=True)
class DirectSkillCall:
    """A high-confidence skill call inferred without another LLM turn."""

    tool_name: str
    tool_input: str
    reason: str


class SkillRouter:
    """Apply narrow heuristics for explicit, deterministic skill requests."""

    _INT_PATTERN = re.compile(r"-?\d+")
    _SUM_N_PATTERN = re.compile(r"1\s*(?:到|-|至)\s*(\d+)")
    _DIRECT_HINTS = (
        "直接调用",
        "直接使用",
        "调用现有工具",
        "用现有工具",
        "use existing tool",
    )
    _RESULT_ONLY_HINTS = ("只返回结果", "只给结果", "only return the result")

    @classmethod
    def infer_direct_skill_call(
        cls,
        *,
        user_input: str,
        candidates: list[SkillCandidate],
    ) -> DirectSkillCall | None:
        normalized = user_input.strip().lower()
        if not normalized:
            return None

        if not any(hint in normalized for hint in cls._DIRECT_HINTS):
            return None

        candidate_names = {item.name for item in candidates}
        preferred = cls._pick_preferred_candidate(normalized, candidate_names)
        if preferred is None:
            return None

        tool_input = cls._infer_tool_input(normalized, preferred)
        if tool_input is None:
            return None

        return DirectSkillCall(
            tool_name=preferred,
            tool_input=tool_input,
            reason="explicit_direct_skill_request",
        )

    @classmethod
    def should_finalize_from_observation(
        cls,
        *,
        user_input: str,
        action_name: str,
        observation: str,
    ) -> bool:
        normalized = user_input.strip().lower()
        if not observation.strip():
            return False
        lowered_observation = observation.strip().lower()
        if "error" in lowered_observation or "not found" in lowered_observation:
            return False
        if any(hint in normalized for hint in cls._RESULT_ONLY_HINTS):
            return True
        return action_name in {"calc_sum_n", "calc_lcm", "fibonacci"} and len(observation) <= 80

    @classmethod
    def _pick_preferred_candidate(
        cls,
        query: str,
        candidate_names: set[str],
    ) -> str | None:
        if "calc_sum_n" in candidate_names and any(
            token in query for token in ("整数和", "求和", "sum")
        ):
            return "calc_sum_n"
        if "calc_lcm" in candidate_names and any(
            token in query for token in ("最小公倍数", "lcm")
        ):
            return "calc_lcm"
        if "fibonacci" in candidate_names and any(
            token in query for token in ("斐波那契", "fibonacci")
        ):
            return "fibonacci"
        return next(iter(candidate_names), None)

    @classmethod
    def _infer_tool_input(cls, query: str, tool_name: str) -> str | None:
        numbers = cls._INT_PATTERN.findall(query)
        if tool_name == "calc_sum_n":
            match = cls._SUM_N_PATTERN.search(query)
            if match:
                return match.group(1)
            if numbers:
                return numbers[-1]
            return None
        if tool_name == "calc_lcm":
            if len(numbers) >= 2:
                return ", ".join(numbers[:2])
            return None
        if tool_name == "fibonacci":
            if numbers:
                return numbers[-1]
            return None
        return None
