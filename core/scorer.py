"""Lightweight scoring module for candidate evaluation.

This scorer is intentionally rule-based and deterministic so it can be used
in both online logging and offline dataset generation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreWeights:
    task: float = 0.45
    format: float = 0.15
    cost: float = 0.15
    memory: float = 0.10
    safety: float = 0.15


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    task: float
    format: float
    cost: float
    memory: float
    safety: float

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "task": self.task,
            "format": self.format,
            "cost": self.cost,
            "memory": self.memory,
            "safety": self.safety,
        }


class RuleBasedScorer:
    """Rule-based scorer following COALA reward layout."""

    def __init__(self, weights: ScoreWeights | None = None):
        self.weights = weights or ScoreWeights()

    def score(
        self,
        response_text: str,
        tool_steps: int,
        memory_hits: int,
        reached_final_answer: bool,
    ) -> ScoreBreakdown:
        task = 1.0 if reached_final_answer else 0.4

        has_final = "Final Answer:" in response_text
        format_score = 1.0 if has_final else 0.6

        # Penalize long tool chains to control latency/cost.
        cost_score = max(-1.0, -0.15 * max(tool_steps - 1, 0))

        # Reward useful memory retrieval but cap quickly.
        memory_score = min(1.0, 0.25 * memory_hits)

        safety_score = self._heuristic_safety(response_text)

        total = (
            self.weights.task * task
            + self.weights.format * format_score
            + self.weights.cost * cost_score
            + self.weights.memory * memory_score
            + self.weights.safety * safety_score
        )
        total = max(0.0, min(1.0, total))

        return ScoreBreakdown(
            total=total,
            task=task,
            format=format_score,
            cost=cost_score,
            memory=memory_score,
            safety=safety_score,
        )

    @staticmethod
    def _heuristic_safety(text: str) -> float:
        lowered = text.lower()
        high_risk_markers = ["password", "token", "api key", "rm -rf", "malware"]
        if any(marker in lowered for marker in high_risk_markers):
            return -1.0
        return 1.0
