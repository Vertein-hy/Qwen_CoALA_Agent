"""Isolated validation workbench for generated skills before persistence."""

from __future__ import annotations

import inspect
from pathlib import Path

from skills.contracts import SkillWorkbenchResult
from skills.tool_contracts import ToolSpec
from skills.validator import SkillValidator


class SkillWorkbench:
    """Validate generated code in an isolated temp workspace before internalization."""

    def __init__(
        self,
        validator: SkillValidator | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self.validator = validator or SkillValidator()
        default_base_dir = Path(__file__).resolve().parent.parent / "tests_runtime" / "skill_workbench"
        self.base_dir = base_dir or default_base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def evaluate(self, *, function_code: str, spec: ToolSpec) -> SkillWorkbenchResult:
        validation = self.validator.validate(function_code)
        if not validation.is_valid:
            return SkillWorkbenchResult(
                is_valid=False,
                function_name=validation.function_name,
                normalized_code=validation.normalized_code,
                errors=validation.errors,
                warnings=validation.warnings,
            )

        if validation.function_name != spec.name:
            return SkillWorkbenchResult(
                is_valid=False,
                function_name=validation.function_name,
                normalized_code=validation.normalized_code,
                errors=(
                    f"Function name '{validation.function_name}' does not match tool contract name '{spec.name}'.",
                ),
                warnings=validation.warnings,
            )

        namespace: dict[str, object] = {}
        pseudo_path = self.base_dir / f"{spec.name}.py"
        try:
            exec(compile(validation.normalized_code, str(pseudo_path), "exec"), namespace)
        except Exception as exc:  # noqa: BLE001
            return SkillWorkbenchResult(
                is_valid=False,
                function_name=validation.function_name,
                normalized_code=validation.normalized_code,
                errors=(f"Workbench execution failed: {exc}",),
                warnings=validation.warnings,
            )

        func = namespace.get(spec.name)
        if not callable(func):
            return SkillWorkbenchResult(
                is_valid=False,
                function_name=validation.function_name,
                normalized_code=validation.normalized_code,
                errors=(f"Function '{spec.name}' not found after execution.",),
                warnings=validation.warnings,
            )

        signature = inspect.signature(func)
        required_params = [
            param.name
            for param in signature.parameters.values()
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            and param.default is inspect._empty
        ]
        required_inputs = [field.name for field in spec.inputs if field.required]
        if required_params != required_inputs:
            return SkillWorkbenchResult(
                is_valid=False,
                function_name=validation.function_name,
                normalized_code=validation.normalized_code,
                errors=(
                    "Function signature does not match required contract inputs. "
                    f"expected={required_inputs}, actual={required_params}",
                ),
                warnings=validation.warnings,
            )

        return SkillWorkbenchResult(
            is_valid=True,
            function_name=validation.function_name,
            normalized_code=validation.normalized_code,
            errors=validation.errors,
            warnings=validation.warnings,
        )
