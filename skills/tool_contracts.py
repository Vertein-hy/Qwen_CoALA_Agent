"""Contracts for project-aware tool discovery, building, and promotion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HelpRequestKind(str, Enum):
    """Structured escalation types for larger-model assistance."""

    SELECT_EXISTING_TOOL = "select_existing_tool"
    REPAIR_TOOL_CONTRACT = "repair_tool_contract"
    PROPOSE_NEW_TOOL = "propose_new_tool"


class PromotionTier(str, Enum):
    """Lifecycle stage for a tool or skill artifact."""

    EPISODE = "episode"
    PROJECT = "project"
    GLOBAL = "global"


@dataclass(frozen=True)
class ToolIOField:
    """One declared input or output field in a tool contract."""

    name: str
    type_name: str
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class ProjectToolContext:
    """Task and environment facts used for tool selection."""

    project_id: str
    task_summary: str
    available_inputs: tuple[str, ...] = ()
    desired_outputs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    environment_facts: tuple[str, ...] = ()
    existing_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    """Contract-first description of a reusable tool."""

    name: str
    purpose: str
    inputs: tuple[ToolIOField, ...]
    outputs: tuple[ToolIOField, ...]
    side_effects: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolMatchBreakdown:
    """Explain why a tool is or is not suitable for a project task."""

    goal_match: float
    io_match: float
    env_match: float
    history_match: float
    risk_penalty: float = 0.0

    @property
    def total_score(self) -> float:
        return (
            self.goal_match
            + self.io_match
            + self.env_match
            + self.history_match
            - self.risk_penalty
        )


@dataclass(frozen=True)
class ToolMatchResult:
    """Ranked result of evaluating one tool against the current task."""

    spec: ToolSpec
    breakdown: ToolMatchBreakdown
    rationale: str


@dataclass(frozen=True)
class ToolBuildRequest:
    """Plan input for creating a new tool when discovery is insufficient."""

    context: ProjectToolContext
    spec: ToolSpec
    preferred_runtime: str = "python"
    test_cases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolBuildReadiness:
    """Whether a draft tool contract is complete enough to implement."""

    ready: bool
    missing_items: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolFailureRecord:
    """One failed attempt that may justify larger-model escalation."""

    stage: str
    reason: str
    attempted_tool: str = ""


@dataclass(frozen=True)
class TeacherRequest:
    """Structured request sent from the small model to the larger model."""

    kind: HelpRequestKind
    goal: str
    current_spec: ToolSpec | None = None
    constraints: tuple[str, ...] = ()
    failures: tuple[ToolFailureRecord, ...] = ()
    requested_output: str = ""


@dataclass(frozen=True)
class ToolExecutionRecord:
    """Observed execution data used for reuse and internalization decisions."""

    tool_name: str
    project_id: str
    success: bool
    matched_contract: bool
    latency_ms: int
    token_cost: int = 0
    reused_existing_tool: bool = False
    internalized_after_run: bool = False
    notes: str = ""


@dataclass(frozen=True)
class PromotionScore:
    """Explicit scoring result for reuse and internalization value."""

    reuse_score: float
    internalize_score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromotionDecision:
    """Decision produced by policy instead of free-form model judgment."""

    tier: PromotionTier
    score: PromotionScore
    should_promote: bool
    explanation: str


@dataclass(frozen=True)
class ToolRegistryRecord:
    """Persisted tool-contract metadata independent of Python skill code."""

    name: str
    project_id: str
    source: str
    origin: str
    tier: PromotionTier
    created_at: str
    updated_at: str
    spec: ToolSpec
    enabled: bool = True
    notes: tuple[str, ...] = ()


@dataclass
class ToolKnowledgeBase:
    """In-memory registry for tool contracts and execution history."""

    specs: list[ToolSpec] = field(default_factory=list)
    executions: list[ToolExecutionRecord] = field(default_factory=list)
