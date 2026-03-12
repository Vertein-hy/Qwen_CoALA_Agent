"""Structured trace recording for agent runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from skills.selector import SkillCandidate
from skills.tool_contracts import ToolMatchResult


@dataclass
class AgentTraceStep:
    """One observable step in the agent loop."""

    kind: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunTrace:
    """Structured execution trace returned to diagnostics surfaces."""

    trace_id: str
    user_input: str
    status: str = "running"
    route: str = ""
    model_name: str = ""
    reply: str = ""
    skill_candidates: list[dict[str, Any]] = field(default_factory=list)
    tool_matches: list[dict[str, Any]] = field(default_factory=list)
    steps: list[AgentTraceStep] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class AgentTraceRecorder:
    """Collect stable trace data without exposing full prompt internals."""

    def __init__(self, *, trace_id: str, user_input: str) -> None:
        self.trace = AgentRunTrace(trace_id=trace_id, user_input=user_input)

    def set_candidates(
        self,
        *,
        skill_candidates: list[SkillCandidate],
        tool_matches: list[ToolMatchResult],
    ) -> None:
        self.trace.skill_candidates = [
            {
                "name": item.name,
                "score": item.score,
                "source_excerpt": item.source_excerpt,
            }
            for item in skill_candidates
        ]
        self.trace.tool_matches = [
            {
                "name": item.spec.name,
                "score": item.breakdown.total_score,
                "purpose": item.spec.purpose,
                "rationale": item.rationale,
            }
            for item in tool_matches
        ]

    def add_step(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace.steps.append(
            AgentTraceStep(
                kind=kind,
                title=title,
                content=content.strip(),
                metadata=metadata or {},
            )
        )

    def finalize(
        self,
        *,
        status: str,
        reply: str,
        route: str,
        model_name: str,
    ) -> dict[str, Any]:
        self.trace.status = status
        self.trace.reply = reply
        self.trace.route = route
        self.trace.model_name = model_name
        return self.trace.to_payload()
