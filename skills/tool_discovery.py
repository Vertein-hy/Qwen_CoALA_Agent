"""Project-aware tool discovery and suitability scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills.tool_contracts import (
    ProjectToolContext,
    ToolKnowledgeBase,
    ToolMatchBreakdown,
    ToolMatchResult,
    ToolSpec,
)


@dataclass
class ToolDiscoveryEngine:
    """Rank known tools for the current project context."""

    knowledge_base: ToolKnowledgeBase
    min_score: float = 1.0

    _LATIN_TOKEN_PATTERN = re.compile(r"[a-z0-9_\-]+", re.IGNORECASE)
    _CJK_SEQ_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")

    def recommend(
        self,
        context: ProjectToolContext,
        top_k: int = 5,
    ) -> list[ToolMatchResult]:
        ranked: list[ToolMatchResult] = []
        for spec in self.knowledge_base.specs:
            result = self.evaluate(context=context, spec=spec)
            if result.breakdown.total_score >= self.min_score:
                ranked.append(result)
        ranked.sort(key=lambda item: item.breakdown.total_score, reverse=True)
        return ranked[: max(0, top_k)]

    def evaluate(
        self,
        *,
        context: ProjectToolContext,
        spec: ToolSpec,
    ) -> ToolMatchResult:
        goal_match = self._goal_match(context, spec)
        io_match = self._io_match(context, spec)
        env_match = self._env_match(context, spec)
        history_match = self._history_match(context, spec)
        risk_penalty = self._risk_penalty(spec)
        breakdown = ToolMatchBreakdown(
            goal_match=goal_match,
            io_match=io_match,
            env_match=env_match,
            history_match=history_match,
            risk_penalty=risk_penalty,
        )
        rationale = (
            f"goal={goal_match:.2f}, io={io_match:.2f}, env={env_match:.2f}, "
            f"history={history_match:.2f}, risk={risk_penalty:.2f}"
        )
        return ToolMatchResult(spec=spec, breakdown=breakdown, rationale=rationale)

    def _goal_match(self, context: ProjectToolContext, spec: ToolSpec) -> float:
        task_tokens = self._tokenize(context.task_summary)
        tool_tokens = self._tokenize(" ".join((spec.name, spec.purpose, *spec.tags)))
        overlap = task_tokens & tool_tokens
        return min(5.0, 0.75 * len(overlap))

    def _io_match(self, context: ProjectToolContext, spec: ToolSpec) -> float:
        available = {item.lower() for item in context.available_inputs}
        desired = {item.lower() for item in context.desired_outputs}
        required_inputs = {field.name.lower() for field in spec.inputs if field.required}
        produced_outputs = {field.name.lower() for field in spec.outputs}
        input_score = 2.0 if required_inputs.issubset(available) else 0.0
        output_overlap = desired & produced_outputs
        output_score = min(3.0, float(len(output_overlap)))
        return input_score + output_score

    def _env_match(self, context: ProjectToolContext, spec: ToolSpec) -> float:
        if not spec.dependencies:
            return 2.0
        facts = " ".join(context.environment_facts).lower()
        matched = sum(1 for dep in spec.dependencies if dep.lower() in facts)
        return min(2.0, 0.5 * matched)

    def _history_match(self, context: ProjectToolContext, spec: ToolSpec) -> float:
        matching_runs = [
            item
            for item in self.knowledge_base.executions
            if item.tool_name == spec.name and item.project_id == context.project_id
        ]
        if not matching_runs:
            return 0.0
        successes = sum(1 for item in matching_runs if item.success)
        return min(2.0, successes * 0.5)

    @staticmethod
    def _risk_penalty(spec: ToolSpec) -> float:
        joined = " ".join(spec.side_effects + spec.failure_modes).lower()
        penalty = 0.0
        for keyword in ("delete", "overwrite", "network", "sudo", "rm "):
            if keyword in joined:
                penalty += 0.5
        return penalty

    def _tokenize(self, text: str) -> set[str]:
        tokens = {
            token.lower()
            for token in self._LATIN_TOKEN_PATTERN.findall(text)
            if token.strip()
        }
        for seq in self._CJK_SEQ_PATTERN.findall(text):
            normalized = seq.strip()
            if len(normalized) < 2:
                continue
            tokens.add(normalized)
            max_n = min(4, len(normalized))
            for n in range(2, max_n + 1):
                for i in range(len(normalized) - n + 1):
                    tokens.add(normalized[i : i + n])
        return tokens
