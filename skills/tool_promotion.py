"""Explicit policy for tool reuse and internalization value."""

from __future__ import annotations

from dataclasses import dataclass

from skills.tool_contracts import (
    PromotionDecision,
    PromotionScore,
    PromotionTier,
    ToolExecutionRecord,
)


@dataclass
class ToolPromotionPolicy:
    """Score completed tool executions for reuse and internalization."""

    project_reuse_threshold: float = 2.5
    global_internalize_threshold: float = 4.0
    min_runs_for_project: int = 2
    min_runs_for_global: int = 3
    min_projects_for_global: int = 2

    def decide(self, executions: list[ToolExecutionRecord]) -> PromotionDecision:
        score = self.score(executions)
        project_span = len({item.project_id for item in executions})
        if (
            len(executions) >= self.min_runs_for_global
            and project_span >= self.min_projects_for_global
            and score.internalize_score >= self.global_internalize_threshold
        ):
            return PromotionDecision(
                tier=PromotionTier.GLOBAL,
                score=score,
                should_promote=True,
                explanation="Tool is stable enough for global internalization.",
            )
        if (
            len(executions) >= self.min_runs_for_project
            and score.reuse_score >= self.project_reuse_threshold
        ):
            return PromotionDecision(
                tier=PromotionTier.PROJECT,
                score=score,
                should_promote=True,
                explanation="Tool should be retained for project-level reuse.",
            )
        return PromotionDecision(
            tier=PromotionTier.EPISODE,
            score=score,
            should_promote=False,
            explanation="Tool is not valuable enough to promote beyond the current episode.",
        )

    def score(self, executions: list[ToolExecutionRecord]) -> PromotionScore:
        if not executions:
            return PromotionScore(0.0, 0.0, ("no_executions",))

        total = len(executions)
        successes = sum(1 for item in executions if item.success)
        contract_matches = sum(1 for item in executions if item.matched_contract)
        reused = sum(1 for item in executions if item.reused_existing_tool)
        projects = {item.project_id for item in executions}

        success_rate = successes / total
        contract_rate = contract_matches / total
        project_span = len(projects)

        reuse_score = round((success_rate * 2.0) + (contract_rate * 1.5) + (reused * 0.5), 2)
        internalize_score = round(reuse_score + min(2.0, project_span * 0.75), 2)

        reasons = [
            f"success_rate={success_rate:.2f}",
            f"contract_rate={contract_rate:.2f}",
            f"project_span={project_span}",
        ]
        return PromotionScore(
            reuse_score=reuse_score,
            internalize_score=internalize_score,
            reasons=tuple(reasons),
        )
