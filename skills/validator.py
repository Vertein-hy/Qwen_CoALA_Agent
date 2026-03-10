"""Validation helpers for generated skill code."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from skills.contracts import SkillValidationResult


@dataclass(frozen=True)
class SkillValidationPolicy:
    """Static policy used to accept or reject generated skills."""

    max_code_chars: int = 8000
    allow_async_functions: bool = False
    banned_import_roots: tuple[str, ...] = (
        "subprocess",
        "socket",
        "http",
        "requests",
        "ftplib",
    )
    banned_call_names: tuple[str, ...] = (
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "input",
    )
    banned_attribute_calls: tuple[str, ...] = (
        "os.system",
        "os.popen",
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_output",
    )


class SkillValidator:
    """Validate code generated for internalized skills."""

    _SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")

    def __init__(self, policy: SkillValidationPolicy | None = None):
        self.policy = policy or SkillValidationPolicy()

    def validate(self, function_code: str) -> SkillValidationResult:
        normalized = self._normalize_code(function_code)
        errors: list[str] = []
        warnings: list[str] = []

        if not normalized:
            return SkillValidationResult(
                is_valid=False,
                normalized_code="",
                errors=("Empty function code.",),
            )
        if len(normalized) > self.policy.max_code_chars:
            errors.append(
                f"Code is too long: {len(normalized)} chars (max={self.policy.max_code_chars})."
            )

        try:
            tree = ast.parse(normalized)
        except SyntaxError as exc:
            return SkillValidationResult(
                is_valid=False,
                normalized_code=normalized,
                errors=(f"Syntax error: {exc.msg} (line {exc.lineno}).",),
            )

        top_level_funcs = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        if len(top_level_funcs) != 1:
            errors.append("Code must contain exactly one top-level function definition.")
            return SkillValidationResult(
                is_valid=False,
                normalized_code=normalized,
                errors=tuple(errors),
            )

        func = top_level_funcs[0]
        if isinstance(func, ast.AsyncFunctionDef) and not self.policy.allow_async_functions:
            errors.append("Async functions are not allowed for internalized skills.")

        if not self._SNAKE_CASE.match(func.name):
            errors.append(f"Function name must be snake_case, got '{func.name}'.")

        if func.name in {"python_repl", "write_file", "read_file"}:
            errors.append(f"Function name '{func.name}' conflicts with built-in tools.")

        docstring = ast.get_docstring(func)
        if not docstring:
            warnings.append("Function has no docstring; maintenance readability may suffer.")

        self._collect_safety_violations(tree=tree, errors=errors)

        return SkillValidationResult(
            is_valid=not errors,
            function_name=func.name if not errors else None,
            normalized_code=normalized,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _normalize_code(function_code: str) -> str:
        text = function_code.strip()
        if text.startswith("```"):
            parts = text.split("\n", 1)
            text = parts[1] if len(parts) > 1 else ""
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        return text.strip()

    def _collect_safety_violations(self, tree: ast.Module, errors: list[str]) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in self.policy.banned_import_roots:
                        errors.append(f"Import '{alias.name}' is not allowed.")
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".", 1)[0]
                if module in self.policy.banned_import_roots:
                    errors.append(f"Import from '{node.module}' is not allowed.")

            if isinstance(node, ast.Call):
                call_name = self._resolve_call_name(node.func)
                if call_name in self.policy.banned_call_names:
                    errors.append(f"Call '{call_name}()' is not allowed.")
                if call_name in self.policy.banned_attribute_calls:
                    errors.append(f"Call '{call_name}()' is not allowed.")

    @staticmethod
    def _resolve_call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts: list[str] = []
            current: ast.AST | None = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""
