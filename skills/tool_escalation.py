"""Structured escalation from the small model to a larger model."""

from __future__ import annotations

from dataclasses import dataclass

from skills.tool_contracts import (
    HelpRequestKind,
    ProjectToolContext,
    TeacherRequest,
    ToolFailureRecord,
    ToolSpec,
)


@dataclass
class TeacherEscalationPlanner:
    """Create compact, structured larger-model requests."""

    max_failures: int = 3

    def create_request(
        self,
        *,
        kind: HelpRequestKind,
        context: ProjectToolContext,
        current_spec: ToolSpec | None,
        failures: list[ToolFailureRecord],
    ) -> TeacherRequest:
        trimmed = tuple(failures[-self.max_failures :])
        requested_output = self._requested_output_for(kind)
        return TeacherRequest(
            kind=kind,
            goal=context.task_summary,
            current_spec=current_spec,
            constraints=context.constraints,
            failures=trimmed,
            requested_output=requested_output,
        )

    @staticmethod
    def _requested_output_for(kind: HelpRequestKind) -> str:
        if kind == HelpRequestKind.SELECT_EXISTING_TOOL:
            return "Return the best matching existing tool and why it fits."
        if kind == HelpRequestKind.REPAIR_TOOL_CONTRACT:
            return "Return a repaired contract with corrected inputs, outputs, and failure modes."
        return "Return a new tool contract that satisfies the goal and constraints."
