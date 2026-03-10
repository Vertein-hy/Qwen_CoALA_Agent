"""Skill metadata catalog persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from skills.contracts import SkillRecord


class SkillCatalog:
    """Maintain lightweight metadata index for internalized skills."""

    def __init__(self, index_file: Path):
        self.index_file = index_file
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self._write_raw({"version": 1, "skills": []})

    def list_records(self) -> list[SkillRecord]:
        payload = self._read_raw()
        records: list[SkillRecord] = []
        for raw in payload.get("skills", []):
            try:
                records.append(
                    SkillRecord(
                        name=str(raw["name"]),
                        source=str(raw.get("source", "")),
                        created_at=str(raw.get("created_at", "")),
                        checksum=str(raw.get("checksum", "")),
                        enabled=bool(raw.get("enabled", True)),
                    )
                )
            except KeyError:
                continue
        return records

    def has_skill(self, name: str) -> bool:
        return any(record.name == name for record in self.list_records())

    def enabled_skill_names(self) -> set[str]:
        return {record.name for record in self.list_records() if record.enabled}

    def add_record(self, *, name: str, source: str, function_code: str) -> SkillRecord:
        payload = self._read_raw()
        now = datetime.now(timezone.utc).isoformat()
        checksum = hashlib.sha256(function_code.encode("utf-8")).hexdigest()
        record = SkillRecord(
            name=name,
            source=source,
            created_at=now,
            checksum=checksum,
            enabled=True,
        )

        skills: list[dict] = [x for x in payload.get("skills", []) if x.get("name") != name]
        skills.append(asdict(record))
        payload["skills"] = skills
        payload.setdefault("version", 1)
        self._write_raw(payload)
        return record

    def _read_raw(self) -> dict:
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "skills": []}

    def _write_raw(self, payload: dict) -> None:
        self.index_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
