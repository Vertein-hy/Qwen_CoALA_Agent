"""JSONL event logger for skill selection and usage telemetry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SkillEventLogger:
    """Append skill events to daily JSONL files."""

    def __init__(self, *, enabled: bool, event_log_dir: Path):
        self.enabled = enabled
        self.event_log_dir = event_log_dir
        if self.enabled:
            self.event_log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, trace_id: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        event = {
            "event_type": event_type,
            "event_ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            **payload,
        }
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.event_log_dir / f"{day}.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
