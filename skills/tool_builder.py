"""Contract-first helpers for tool construction."""

from __future__ import annotations

from dataclasses import dataclass

from skills.tool_contracts import ToolBuildReadiness, ToolBuildRequest, ToolSpec


@dataclass
class ToolBuilderPlanner:
    """Validate a tool contract before implementation starts."""

    def assess_readiness(self, spec: ToolSpec) -> ToolBuildReadiness:
        missing: list[str] = []
        warnings: list[str] = []

        if not spec.name.strip():
            missing.append("name")
        if not spec.purpose.strip():
            missing.append("purpose")
        if not spec.inputs:
            missing.append("inputs")
        if not spec.outputs:
            missing.append("outputs")
        if not spec.failure_modes:
            warnings.append("failure_modes_not_declared")
        if not spec.examples:
            warnings.append("examples_not_declared")

        return ToolBuildReadiness(
            ready=not missing,
            missing_items=tuple(missing),
            warnings=tuple(warnings),
        )

    def build_outline(self, request: ToolBuildRequest) -> str:
        """Return an implementation outline for the small model to follow."""

        inputs = ", ".join(f"{field.name}:{field.type_name}" for field in request.spec.inputs)
        outputs = ", ".join(f"{field.name}:{field.type_name}" for field in request.spec.outputs)
        return (
            f"Tool: {request.spec.name}\n"
            f"Purpose: {request.spec.purpose}\n"
            f"Inputs: {inputs}\n"
            f"Outputs: {outputs}\n"
            f"Runtime: {request.preferred_runtime}\n"
            "Steps:\n"
            "1. Validate required inputs.\n"
            "2. Execute core logic.\n"
            "3. Return only the declared outputs.\n"
            "4. Handle declared failure modes explicitly.\n"
        )
