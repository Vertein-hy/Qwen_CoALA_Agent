from __future__ import annotations

import json
from pathlib import Path

from skills.runtime_loader import SkillPluginLoader


def test_runtime_loader_filters_by_index(tmp_path: Path) -> None:
    skill_file = tmp_path / "custom_skills.py"
    index_file = tmp_path / "index.json"
    skill_file.write_text(
        """
def keep_me():
    return "ok"

def skip_me():
    return "no"
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    index_file.write_text(
        json.dumps(
            {
                "version": 1,
                "skills": [
                    {
                        "name": "keep_me",
                        "source": "test",
                        "created_at": "2026-01-01T00:00:00Z",
                        "checksum": "x",
                        "enabled": True,
                    },
                    {
                        "name": "skip_me",
                        "source": "test",
                        "created_at": "2026-01-01T00:00:00Z",
                        "checksum": "y",
                        "enabled": False,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loader = SkillPluginLoader(skills_file=skill_file, index_file=index_file)
    loaded = loader.load()

    assert "keep_me" in loaded
    assert "skip_me" not in loaded


def test_runtime_loader_returns_empty_when_skill_file_has_syntax_error(tmp_path: Path) -> None:
    skill_file = tmp_path / "custom_skills.py"
    skill_file.write_text(
        """
def broken():
    返回 1
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    loader = SkillPluginLoader(skills_file=skill_file)
    loaded = loader.load()

    assert loaded == {}
