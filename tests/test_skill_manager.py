from __future__ import annotations

from pathlib import Path

import pytest

from skills.manager import SkillManager


def _build_manager(tmp_path: Path) -> SkillManager:
    return SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )


def test_append_skill_writes_file_and_catalog(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)

    name = manager.append_skill(
        source="unit-test",
        function_code="""
def add_two(value):
    \"\"\"Add 2.\"\"\"
    return value + 2
        """,
    )

    assert name == "add_two"
    assert manager.has_skill("add_two")
    assert manager.list_skills() == ["add_two"]
    content = (tmp_path / "custom_skills.py").read_text(encoding="utf-8")
    assert "def add_two(" in content


def test_append_skill_rejects_duplicate_name(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)
    manager.append_skill(
        source="first",
        function_code="""
def dedupe_name(value):
    return value
        """,
    )

    with pytest.raises(ValueError, match="already exists"):
        manager.append_skill(
            source="second",
            function_code="""
def dedupe_name(value):
    return value + 1
            """,
        )


def test_append_skill_rejects_invalid_code(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)

    with pytest.raises(ValueError, match="validation failed"):
        manager.append_skill(
            source="invalid",
            function_code="""
def not_safe():
    import subprocess
    return subprocess.run(["echo", "x"])
            """,
        )


def test_append_skill_escapes_multiline_source_prompt(tmp_path: Path) -> None:
    manager = _build_manager(tmp_path)
    manager.append_skill(
        source="[small]\n请按 ReAct\ndef calc_sum_n(n): ...\n最后输出",
        function_code="""
def calc_sum_n(n):
    \"\"\"Return sum from 1 to n.\"\"\"
    return sum(range(1, n + 1))
        """,
    )

    content = (tmp_path / "custom_skills.py").read_text(encoding="utf-8")
    assert "\ndef calc_sum_n(n): ...\n" not in content
    assert "#         def calc_sum_n(n): ..." in content
