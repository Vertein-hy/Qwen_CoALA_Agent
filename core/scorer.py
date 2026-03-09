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
    R_total: float
    R_task: float
    R_format: float
    R_cost: float
    R_memory: float
    R_safety: float

    def as_dict(self) -> dict:
        # Keep both canonical R_* keys and legacy keys for compatibility.
        return {
            "R_total": self.R_total,
            "R_task": self.R_task,
            "R_format": self.R_format,
            "R_cost": self.R_cost,
            "R_memory": self.R_memory,
            "R_safety": self.R_safety,
            "total": self.R_total,
            "task": self.R_task,
            "format": self.R_format,
            "cost": self.R_cost,
            "memory": self.R_memory,
            "safety": self.R_safety,
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
            R_total=total,
            R_task=task,
            R_format=format_score,
            R_cost=cost_score,
            R_memory=memory_score,
            R_safety=safety_score,
        )

    @staticmethod
    def _heuristic_safety(text: str) -> float:
        lowered = text.lower()
        high_risk_markers = ["password", "token", "api key", "rm -rf", "malware"]
        if any(marker in lowered for marker in high_risk_markers):
            return -1.0
        return 1.0
