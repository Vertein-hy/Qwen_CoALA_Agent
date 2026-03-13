"""Runtime bridge that turns current execution context into policy suggestions."""

from __future__ import annotations

from rl.contracts import DecisionState, PolicySuggestion
from rl.policy import LinearDecisionPolicy


class RLRuntimeRouter:
    """Non-invasive runtime helper for decision-layer policy suggestions."""

    def __init__(self, policy: LinearDecisionPolicy | None = None) -> None:
        self.policy = policy or LinearDecisionPolicy()

    def build_state(
        self,
        *,
        user_input: str,
        skill_candidates: list[dict] | list[object],
        tool_matches: list[dict] | list[object],
        steps: list[dict] | list[object] | None = None,
        route_hint: str = "",
    ) -> DecisionState:
        skill_scores = [self._extract_score(item) for item in skill_candidates]
        tool_scores = [self._extract_score(item) for item in tool_matches]
        trace_steps = steps or []

        return DecisionState(
            user_input=user_input,
            skill_candidate_count=len(skill_candidates),
            tool_match_count=len(tool_matches),
            top_skill_score=max(skill_scores) if skill_scores else 0.0,
            top_tool_score=max(tool_scores) if tool_scores else 0.0,
            has_tool_spec=any(self._extract_kind(item) == "tool_spec" for item in trace_steps),
            repeated_tool_error=self._has_repeated_error(trace_steps),
            current_step_count=len(trace_steps),
            route_hint=route_hint,
        )

    def suggest(
        self,
        *,
        user_input: str,
        skill_candidates: list[dict] | list[object],
        tool_matches: list[dict] | list[object],
        steps: list[dict] | list[object] | None = None,
        route_hint: str = "",
    ) -> PolicySuggestion:
        state = self.build_state(
            user_input=user_input,
            skill_candidates=skill_candidates,
            tool_matches=tool_matches,
            steps=steps,
            route_hint=route_hint,
        )
        return self.policy.suggest(state)

    @staticmethod
    def _extract_score(item: dict | object) -> float:
        if isinstance(item, dict):
            return float(item.get("score", 0.0) or 0.0)
        return float(getattr(item, "score", 0.0) or 0.0)

    @staticmethod
    def _extract_kind(item: dict | object) -> str:
        if isinstance(item, dict):
            return str(item.get("kind", ""))
        return str(getattr(item, "kind", ""))

    @classmethod
    def _has_repeated_error(cls, steps: list[dict] | list[object]) -> bool:
        errors = 0
        for item in steps:
            kind = cls._extract_kind(item)
            if kind != "observation":
                continue
            content = item.get("content", "") if isinstance(item, dict) else getattr(item, "content", "")
            lowered = str(content).lower()
            if "python error" in lowered or "tool not found" in lowered or "file does not exist" in lowered:
                errors += 1
        return errors >= 2
