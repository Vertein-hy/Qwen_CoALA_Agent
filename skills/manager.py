"""Skill persistence and lookup utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillManager:
    skill_file: Path = Path("skills/internalized/custom_skills.py")

    def __post_init__(self) -> None:
        self.skill_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.skill_file.exists():
            self.skill_file.write_text(
                "# Auto-generated internalized skills\n",
                encoding="utf-8",
            )

    def has_skill(self, func_name: str) -> bool:
        content = self.skill_file.read_text(encoding="utf-8")
        return f"def {func_name}(" in content

    def append_skill(self, source: str, function_code: str) -> None:
        with self.skill_file.open("a", encoding="utf-8") as f:
            f.write(f"\n\n# Source: {source}\n")
            f.write(function_code.strip() + "\n")
