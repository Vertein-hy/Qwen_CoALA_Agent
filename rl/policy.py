"""Lightweight contextual policy for decision-layer recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field

from rl.contracts import DecisionAction, DecisionSample, DecisionState, PolicySuggestion


DEFAULT_FEATURES = (
    "bias",
    "tool_match_count",
    "top_tool_score",
    "skill_candidate_count",
    "top_skill_score",
    "has_tool_spec",
    "repeated_tool_error",
    "current_step_count",
    "mentions_http_route",
)

HTTP_ROUTE_HINT_TOKENS = (
    "http",
    "api",
    "route",
    "routes",
    "routing",
    "路由",
    "接口",
    "摘要",
    "markdown",
)


@dataclass
class LinearDecisionPolicy:
    """A simple linear scorer that can be updated from offline samples."""

    weights: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.weights:
            return
        self.weights = {
            DecisionAction.DIRECT_TOOL.value: {
                "bias": 0.1,
                "tool_match_count": 0.3,
                "top_tool_score": 0.9,
                "mentions_http_route": 1.4,
            },
            DecisionAction.BUILD_TOOL.value: {
                "bias": -0.1,
                "has_tool_spec": 1.1,
                "tool_match_count": -0.4,
            },
            DecisionAction.ASK_TEACHER.value: {
                "bias": -0.2,
                "has_tool_spec": 0.7,
                "repeated_tool_error": 1.2,
                "current_step_count": 0.2,
            },
            DecisionAction.FINALIZE.value: {
                "bias": 0.0,
                "current_step_count": 0.15,
                "repeated_tool_error": -0.8,
            },
            DecisionAction.CONTINUE.value: {
                "bias": 0.05,
                "current_step_count": 0.05,
            },
        }

    def suggest(self, state: DecisionState) -> PolicySuggestion:
        features = self._features(state)
        scores = {action: self._score_action(action, features) for action in self.weights}
        best_action_name, best_score = max(scores.items(), key=lambda item: item[1])
        sorted_scores = sorted(scores.values(), reverse=True)
        runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        confidence = best_score - runner_up
        action = DecisionAction(best_action_name)
        return PolicySuggestion(
            action=action,
            confidence=round(confidence, 4),
            rationale=f"linear_policy score={best_score:.3f}",
            scores=scores,
        )

    def update_from_samples(self, samples: list[DecisionSample], learning_rate: float = 0.05) -> None:
        for sample in samples:
            features = self._features(sample.state)
            predicted = self.suggest(sample.state).action
            if predicted == sample.action:
                self._shift(sample.action, features, learning_rate * sample.reward)
                continue
            self._shift(sample.action, features, learning_rate * max(sample.reward, 0.1))
            self._shift(predicted, features, -learning_rate * max(sample.reward, 0.1))

    def _features(self, state: DecisionState) -> dict[str, float]:
        lowered = state.user_input.lower()
        return {
            "bias": 1.0,
            "tool_match_count": float(state.tool_match_count),
            "top_tool_score": float(state.top_tool_score),
            "skill_candidate_count": float(state.skill_candidate_count),
            "top_skill_score": float(state.top_skill_score),
            "has_tool_spec": 1.0 if state.has_tool_spec else 0.0,
            "repeated_tool_error": 1.0 if state.repeated_tool_error else 0.0,
            "current_step_count": float(state.current_step_count),
            "mentions_http_route": 1.0 if any(token in lowered for token in HTTP_ROUTE_HINT_TOKENS) else 0.0,
        }

    def _score_action(self, action: str, features: dict[str, float]) -> float:
        weights = self.weights.get(action, {})
        return round(sum(weights.get(name, 0.0) * value for name, value in features.items()), 6)

    def _shift(self, action: DecisionAction, features: dict[str, float], scale: float) -> None:
        table = self.weights.setdefault(action.value, {})
        for feature_name in DEFAULT_FEATURES:
            value = features.get(feature_name, 0.0)
            if value == 0.0:
                continue
            table[feature_name] = table.get(feature_name, 0.0) + (scale * value)
