"""Skill evolution module.

Transforms successful ad-hoc code into reusable internalized skills.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.llm_interface import LLMInterface
from skills.manager import SkillManager


@dataclass
class SkillEvolver:
    llm: LLMInterface
    skill_manager: SkillManager

    def evolve(self, user_intent: str, successful_code: str) -> bool:
        """Try to convert successful code into reusable function.

        Returns True if a new skill is persisted.
        """

        prompt = f"""
You are a Python refactoring assistant.
Convert the following code into one reusable function.
Requirements:
1) Output Python function code only.
2) Function name must be snake_case.
3) Prefer generic parameters over hardcoded constants.

User intent:
{user_intent}

Code:
{successful_code}
"""

        function_code = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            route_hint="large",
        )
        function_code = function_code.replace("```python", "").replace("```", "").strip()

        if "def " not in function_code:
            return False

        func_name = self._extract_function_name(function_code)
        if not func_name:
            return False

        if self.skill_manager.has_skill(func_name):
            return False

        self.skill_manager.append_skill(source=user_intent, function_code=function_code)
        return True

    @staticmethod
    def _extract_function_name(code: str) -> str | None:
        match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code)
        return match.group(1) if match else None
