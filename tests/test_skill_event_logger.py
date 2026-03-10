from __future__ import annotations

import json
from pathlib import Path

from skills.event_logger import SkillEventLogger


def test_skill_event_logger_writes_jsonl(tmp_path: Path) -> None:
    logger = SkillEventLogger(
        enabled=True,
        event_log_dir=tmp_path,
    )
    logger.log(
        "skill_called",
        "tr_test",
        {"tool_name": "calc_sum_n"},
    )

    files = list(tmp_path.glob("*.jsonl"))
    assert files
    payload = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert payload["event_type"] == "skill_called"
    assert payload["trace_id"] == "tr_test"
    assert payload["tool_name"] == "calc_sum_n"


def test_skill_event_logger_respects_disabled_flag(tmp_path: Path) -> None:
    logger = SkillEventLogger(
        enabled=False,
        event_log_dir=tmp_path,
    )
    logger.log(
        "skill_called",
        "tr_test",
        {"tool_name": "calc_sum_n"},
    )
    assert list(tmp_path.glob("*.jsonl")) == []
