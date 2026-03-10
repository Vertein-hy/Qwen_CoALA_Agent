from __future__ import annotations

from pathlib import Path

from skills.manager import SkillManager
from skills.selector import SkillSelector


def _build_manager(tmp_path: Path) -> SkillManager:
    return SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )


def test_selector_ranks_matching_skill_highest(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)
    manager.append_skill(
        source="用于计算 1 到 n 的求和",
        function_code="""
def calc_sum_n(n):
    \"\"\"Return sum from 1 to n.\"\"\"
    return sum(range(1, n + 1))
        """,
    )
    manager.append_skill(
        source="用于将字符串转为大写",
        function_code="""
def to_upper_text(text):
    \"\"\"Uppercase a string.\"\"\"
    return text.upper()
        """,
    )

    selector = SkillSelector(manager)
    ranked = selector.recommend("请帮我计算从1到100求和", top_k=2)

    assert ranked
    assert ranked[0].name == "calc_sum_n"
    assert ranked[0].score > 0
