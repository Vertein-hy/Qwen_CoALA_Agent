"""Persistence for candidate and promoted tool contracts."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from skills.tool_contracts import (
    PromotionDecision,
    PromotionTier,
    ToolExecutionRecord,
    ToolIOField,
    ToolRegistryRecord,
    ToolSpec,
)


class ToolRegistry:
    """Store structured tool specs plus execution history in JSON."""

    def __init__(self, index_file: Path):
        self.index_file = index_file
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self._write_raw({"version": 1, "tools": [], "executions": []})

    def list_records(self) -> list[ToolRegistryRecord]:
        payload = self._read_raw()
        records: list[ToolRegistryRecord] = []
        for raw in payload.get("tools", []):
            record = self._parse_record(raw)
            if record is not None:
                records.append(record)
        return records

    def list_specs(self) -> list[ToolSpec]:
        return [record.spec for record in self.list_records() if record.enabled]

    def get_record(self, name: str) -> ToolRegistryRecord | None:
        for record in self.list_records():
            if record.name == name:
                return record
        return None

    def has_tool(self, name: str) -> bool:
        return self.get_record(name) is not None

    def upsert_spec(
        self,
        *,
        spec: ToolSpec,
        project_id: str,
        source: str,
        origin: str,
        tier: PromotionTier = PromotionTier.EPISODE,
        note: str = "",
    ) -> ToolRegistryRecord:
        payload = self._read_raw()
        now = datetime.now(timezone.utc).isoformat()
        records = payload.get("tools", [])
        existing = next((item for item in records if item.get("name") == spec.name), None)
        created_at = str(existing.get("created_at")) if isinstance(existing, dict) and existing.get("created_at") else now
        notes = self._merge_notes(existing.get("notes") if isinstance(existing, dict) else [], note)
        record = ToolRegistryRecord(
            name=spec.name,
            project_id=project_id,
            source=source,
            origin=origin,
            tier=tier,
            created_at=created_at,
            updated_at=now,
            spec=spec,
            enabled=True,
            notes=notes,
            implementation_code=(
                str(existing.get("implementation_code", ""))
                if isinstance(existing, dict)
                else ""
            ),
        )
        filtered = [item for item in records if item.get("name") != spec.name]
        filtered.append(self._record_to_dict(record))
        payload["tools"] = filtered
        payload.setdefault("executions", [])
        self._write_raw(payload)
        return record

    def add_execution(self, execution: ToolExecutionRecord) -> None:
        payload = self._read_raw()
        raw = asdict(execution)
        executions = payload.get("executions", [])
        executions.append(raw)
        payload["executions"] = executions
        payload.setdefault("tools", [])
        self._write_raw(payload)

    def attach_implementation(self, tool_name: str, function_code: str) -> ToolRegistryRecord | None:
        payload = self._read_raw()
        updated = False
        result: ToolRegistryRecord | None = None
        records: list[dict] = []
        for raw in payload.get("tools", []):
            if raw.get("name") != tool_name:
                records.append(raw)
                continue
            parsed = self._parse_record(raw)
            if parsed is None:
                continue
            updated_record = ToolRegistryRecord(
                name=parsed.name,
                project_id=parsed.project_id,
                source=parsed.source,
                origin=parsed.origin,
                tier=parsed.tier,
                created_at=parsed.created_at,
                updated_at=datetime.now(timezone.utc).isoformat(),
                spec=parsed.spec,
                enabled=parsed.enabled,
                notes=self._merge_notes(parsed.notes, "implementation_attached"),
                implementation_code=function_code.strip(),
            )
            records.append(self._record_to_dict(updated_record))
            updated = True
            result = updated_record
        if updated:
            payload["tools"] = records
            self._write_raw(payload)
        return result

    def executions_for(self, tool_name: str) -> list[ToolExecutionRecord]:
        payload = self._read_raw()
        out: list[ToolExecutionRecord] = []
        for raw in payload.get("executions", []):
            if raw.get("tool_name") != tool_name:
                continue
            try:
                out.append(
                    ToolExecutionRecord(
                        tool_name=str(raw.get("tool_name", "")),
                        project_id=str(raw.get("project_id", "")),
                        success=bool(raw.get("success", False)),
                        matched_contract=bool(raw.get("matched_contract", False)),
                        latency_ms=int(raw.get("latency_ms", 0)),
                        token_cost=int(raw.get("token_cost", 0)),
                        reused_existing_tool=bool(raw.get("reused_existing_tool", False)),
                        internalized_after_run=bool(raw.get("internalized_after_run", False)),
                        notes=str(raw.get("notes", "")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return out

    def apply_promotion(self, tool_name: str, decision: PromotionDecision) -> ToolRegistryRecord | None:
        payload = self._read_raw()
        updated = False
        result: ToolRegistryRecord | None = None
        records: list[dict] = []
        for raw in payload.get("tools", []):
            if raw.get("name") != tool_name:
                records.append(raw)
                continue
            parsed = self._parse_record(raw)
            if parsed is None:
                continue
            note = f"promotion={decision.tier.value}; should_promote={decision.should_promote}; explanation={decision.explanation}"
            upgraded = ToolRegistryRecord(
                name=parsed.name,
                project_id=parsed.project_id,
                source=parsed.source,
                origin=parsed.origin,
                tier=decision.tier if decision.should_promote else parsed.tier,
                created_at=parsed.created_at,
                updated_at=datetime.now(timezone.utc).isoformat(),
                spec=parsed.spec,
                enabled=parsed.enabled,
                notes=self._merge_notes(parsed.notes, note),
                implementation_code=parsed.implementation_code,
            )
            records.append(self._record_to_dict(upgraded))
            updated = True
            result = upgraded
        if updated:
            payload["tools"] = records
            self._write_raw(payload)
        return result

    def _parse_record(self, raw: object) -> ToolRegistryRecord | None:
        if not isinstance(raw, dict):
            return None
        spec_raw = raw.get("spec")
        if not isinstance(spec_raw, dict):
            return None
        try:
            tier = PromotionTier(str(raw.get("tier", PromotionTier.EPISODE.value)))
        except ValueError:
            tier = PromotionTier.EPISODE
        spec = ToolSpec(
            name=str(spec_raw.get("name", "")).strip(),
            purpose=str(spec_raw.get("purpose", "")).strip(),
            inputs=self._parse_fields(spec_raw.get("inputs")),
            outputs=self._parse_fields(spec_raw.get("outputs")),
            side_effects=self._parse_str_tuple(spec_raw.get("side_effects")),
            failure_modes=self._parse_str_tuple(spec_raw.get("failure_modes")),
            examples=self._parse_str_tuple(spec_raw.get("examples")),
            dependencies=self._parse_str_tuple(spec_raw.get("dependencies")),
            tags=self._parse_str_tuple(spec_raw.get("tags")),
        )
        if not spec.name:
            return None
        return ToolRegistryRecord(
            name=str(raw.get("name", spec.name)),
            project_id=str(raw.get("project_id", "")),
            source=str(raw.get("source", "")),
            origin=str(raw.get("origin", "")),
            tier=tier,
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
            spec=spec,
            enabled=bool(raw.get("enabled", True)),
            notes=self._parse_str_tuple(raw.get("notes")),
            implementation_code=str(raw.get("implementation_code", "")),
        )

    def _record_to_dict(self, record: ToolRegistryRecord) -> dict:
        data = asdict(record)
        data["tier"] = record.tier.value
        return data

    def _read_raw(self) -> dict:
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "tools": [], "executions": []}

    def _write_raw(self, payload: dict) -> None:
        self.index_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _parse_fields(value: object) -> tuple[ToolIOField, ...]:
        if not isinstance(value, list):
            return ()
        out: list[ToolIOField] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            out.append(
                ToolIOField(
                    name=str(item.get("name", "")).strip(),
                    type_name=str(item.get("type_name", item.get("type", ""))).strip(),
                    required=bool(item.get("required", True)),
                    description=str(item.get("description", "")).strip(),
                )
            )
        return tuple(out)

    @staticmethod
    def _parse_str_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())

    @staticmethod
    def _merge_notes(existing: object, note: str) -> tuple[str, ...]:
        merged: list[str] = []
        if isinstance(existing, list):
            merged.extend(str(item).strip() for item in existing if str(item).strip())
        elif isinstance(existing, tuple):
            merged.extend(str(item).strip() for item in existing if str(item).strip())
        if note.strip():
            merged.append(note.strip())
        deduped: list[str] = []
        for item in merged:
            if item not in deduped:
                deduped.append(item)
        return tuple(deduped[-6:])
