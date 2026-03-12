"""Parsers for structured tool lifecycle blocks emitted by the model."""

from __future__ import annotations

import json
import re

from skills.tool_contracts import ToolIOField, ToolSpec


class ToolLifecycleParser:
    """Extract structured tool specs from model output."""

    _TOOL_SPEC_BLOCK = re.compile(r"```tool_spec\s*([\s\S]*?)```", re.IGNORECASE)

    @classmethod
    def parse_tool_spec(cls, text: str) -> ToolSpec | None:
        payload = cls._extract_json_payload(text)
        if payload is None:
            return None
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        return ToolSpec(
            name=str(data.get("name", "")).strip(),
            purpose=str(data.get("purpose", "")).strip(),
            inputs=cls._parse_fields(data.get("inputs")),
            outputs=cls._parse_fields(data.get("outputs")),
            side_effects=cls._parse_str_tuple(data.get("side_effects")),
            failure_modes=cls._parse_str_tuple(data.get("failure_modes")),
            examples=cls._parse_str_tuple(data.get("examples")),
            dependencies=cls._parse_str_tuple(data.get("dependencies")),
            tags=cls._parse_str_tuple(data.get("tags")),
        )

    @classmethod
    def _extract_json_payload(cls, text: str) -> str | None:
        match = cls._TOOL_SPEC_BLOCK.search(text)
        if match:
            return match.group(1).strip()
        marker = "Tool Spec:"
        if marker in text:
            return text.split(marker, 1)[-1].strip()
        return None

    @staticmethod
    def _parse_fields(value: object) -> tuple[ToolIOField, ...]:
        if not isinstance(value, list):
            return ()
        fields: list[ToolIOField] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            fields.append(
                ToolIOField(
                    name=str(item.get("name", "")).strip(),
                    type_name=str(item.get("type_name", item.get("type", ""))).strip(),
                    required=bool(item.get("required", True)),
                    description=str(item.get("description", "")).strip(),
                )
            )
        return tuple(fields)

    @staticmethod
    def _parse_str_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())
