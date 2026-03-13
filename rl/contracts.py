"""Contracts for decision-layer reinforcement learning scaffolding."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DecisionAction(str, Enum):
    """Discrete actions that the decision policy may recommend."""

    DIRECT_TOOL = "direct_tool"
    BUILD_TOOL = "build_tool"
    ASK_TEACHER = "ask_teacher"
    FINALIZE = "finalize"
    CONTINUE = "continue"


@dataclass(frozen=True)
class DecisionState:
    """Compact state observed before the agent chooses its next high-level step."""

    user_input: str
    skill_candidate_count: int = 0
    tool_match_count: int = 0
    top_skill_score: float = 0.0
    top_tool_score: float = 0.0
    has_tool_spec: bool = False
    repeated_tool_error: bool = False
    current_step_count: int = 0
    route_hint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionSample:
    """One offline sample for learning or evaluating routing decisions."""

    trace_id: str
    state: DecisionState
    action: DecisionAction
    reward: float
    outcome: str
    next_state: DecisionState | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


@dataclass(frozen=True)
class PolicySuggestion:
    """Policy output used by the runtime router without exposing model internals."""

    action: DecisionAction
    confidence: float
    rationale: str
    scores: dict[str, float] = field(default_factory=dict)
