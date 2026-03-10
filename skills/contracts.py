"""Skill subsystem contracts and data carriers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillValidationResult:
    """Outcome of validating generated skill code before persistence."""

    is_valid: bool
    function_name: str | None = None
    normalized_code: str = ""
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SkillRecord:
    """Persisted metadata for one internalized skill."""

    name: str
    source: str
    created_at: str
    checksum: str
    enabled: bool = True
