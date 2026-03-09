from __future__ import annotations

from core.scorer import RuleBasedScorer


def test_rule_scorer_returns_r_prefixed_fields() -> None:
    scorer = RuleBasedScorer()
    score = scorer.score(
        response_text="Final Answer: done",
        tool_steps=2,
        memory_hits=2,
        reached_final_answer=True,
    )
    payload = score.as_dict()

    for key in ["R_total", "R_task", "R_format", "R_cost", "R_memory", "R_safety"]:
        assert key in payload

    # Legacy keys remain for compatibility with existing downstream code.
    for key in ["total", "task", "format", "cost", "memory", "safety"]:
        assert key in payload
