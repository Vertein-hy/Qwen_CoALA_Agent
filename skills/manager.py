"""Skill persistence and validation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from skills.catalog import SkillCatalog
from skills.contracts import SkillValidationResult
from skills.validator import SkillValidator


@dataclass
class SkillManager:
    skill_file: Path = Path("skills/internalized/custom_skills.py")
    index_file: Path = Path("skills/internalized/index.json")
    validator: SkillValidator = field(default_factory=SkillValidator)
    catalog: SkillCatalog = field(init=False)

    def __post_init__(self) -> None:
        self.skill_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.skill_file.exists():
            self.skill_file.write_text(
                "# Auto-generated internalized skills\n",
                encoding="utf-8",
            )
        self.catalog = SkillCatalog(index_file=self.index_file)

    def has_skill(self, func_name: str) -> bool:
        if self.catalog.has_skill(func_name):
            return True
        content = self.skill_file.read_text(encoding="utf-8")
        return f"def {func_name}(" in content

    def append_skill(self, source: str, function_code: str) -> str:
        validation = self.validate(function_code)
        if not validation.is_valid or not validation.function_name:
            reasons = "; ".join(validation.errors) or "unknown validation error"
            raise ValueError(f"Skill validation failed: {reasons}")

        if self.has_skill(validation.function_name):
            raise ValueError(f"Skill '{validation.function_name}' already exists.")

        with self.skill_file.open("a", encoding="utf-8") as f:
            f.write(f"\n\n# Source: {source}\n")
            f.write(validation.normalized_code.strip() + "\n")
        self.catalog.add_record(
            name=validation.function_name,
            source=source,
            function_code=validation.normalized_code.strip(),
        )
        return validation.function_name

    def validate(self, function_code: str) -> SkillValidationResult:
        return self.validator.validate(function_code)

    def list_skills(self) -> list[str]:
        return sorted(record.name for record in self.catalog.list_records() if record.enabled)
