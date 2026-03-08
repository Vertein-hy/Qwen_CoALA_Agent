"""Utilities for parsing ReAct-style model outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedAction:
    tool_name: str
    tool_input: str


class ReActParser:
    action_pattern = re.compile(r"Action:\s*(.*?)(?:\n|$)", re.IGNORECASE)
    input_pattern = re.compile(
        r"Action Input:\s*([\s\S]*?)(?:\nObservation:|$)",
        re.IGNORECASE,
    )

    @classmethod
    def parse_action(cls, text: str) -> ParsedAction | None:
        action_match = cls.action_pattern.search(text)
        input_match = cls.input_pattern.search(text)
        if not action_match or not input_match:
            return None

        tool_name = action_match.group(1).strip()
        tool_input = input_match.group(1).strip()
        if "Observation:" in tool_input:
            tool_input = tool_input.split("Observation:", 1)[0].strip()

        return ParsedAction(tool_name=tool_name, tool_input=tool_input)

    @staticmethod
    def parse_final_answer(text: str) -> str | None:
        marker = "Final Answer:"
        if marker not in text:
            return None
        return text.split(marker, 1)[-1].strip()
