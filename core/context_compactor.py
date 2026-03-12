"""Compact loop context for small-model execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from skills.tool_contracts import ToolMatchResult, ToolSpec


@dataclass
class LoopExecutionState:
    """Deterministic state snapshot kept stable across long reasoning loops."""

    goal: str = ""
    current_focus: str = ""
    next_step: str = ""
    ranked_tools: tuple[str, ...] = ()
    active_contract: str = ""
    teacher_guidance: str = ""
    recent_observations: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)


class LoopContextCompactor:
    """Compress raw loop traffic into a stable task brief plus recent turns."""

    _ACTION_RE = re.compile(r"Action:\s*([^\n]+)", re.IGNORECASE)

    def __init__(
        self,
        *,
        keep_recent_messages: int = 6,
        compress_trigger: int = 10,
        max_items: int = 4,
        text_limit: int = 220,
    ) -> None:
        self.keep_recent_messages = max(2, keep_recent_messages)
        self.compress_trigger = max(self.keep_recent_messages + 1, compress_trigger)
        self.max_items = max(2, max_items)
        self.text_limit = max(80, text_limit)
        self.state = LoopExecutionState()

    def start_run(self, *, goal: str, tool_matches: list[ToolMatchResult]) -> None:
        self.state.goal = self._clip(goal)
        self.state.ranked_tools = tuple(match.spec.name for match in tool_matches[:3])
        self.state.current_focus = "understand the goal and choose the next safe action"
        self.state.next_step = "reuse an existing tool when it fits; otherwise define a Tool Spec"

    def record_action(self, tool_name: str, tool_input: str) -> None:
        self.state.current_focus = f"executing tool {tool_name}"
        self.state.next_step = f"inspect the observation from {tool_name}"
        summary = tool_name
        if tool_input.strip():
            summary = f"{tool_name}: {self._clip(self._first_line(tool_input), limit=120)}"
        self._push_unique(self.state.completed_steps, f"planned {summary}")

    def record_observation(self, observation: str) -> None:
        line = self._clip(self._first_line(observation))
        if line:
            self._push(self.state.recent_observations, line)
        self.state.current_focus = "evaluate the latest observation"

    def record_tool_spec(self, spec: ToolSpec, *, source: str) -> None:
        name = spec.name or "(unnamed_tool)"
        inputs = ", ".join(field.name for field in spec.inputs[:3]) or "none"
        outputs = ", ".join(field.name for field in spec.outputs[:3]) or "none"
        purpose = spec.purpose or "(missing purpose)"
        self.state.active_contract = self._clip(
            f"{source}:{name} | inputs=[{inputs}] | outputs=[{outputs}] | purpose={purpose}"
        )
        self.state.current_focus = f"validate tool contract {name}"
        self.state.next_step = "repair missing contract fields or implement the accepted contract"

    def record_teacher_guidance(self, guidance: str) -> None:
        stripped = self._strip_code_blocks(guidance)
        self.state.teacher_guidance = self._clip(self._first_line(stripped))
        self.state.current_focus = "apply teacher guidance to repair the contract"
        self.state.next_step = "turn the repaired contract into an implementation step"

    def record_completion(self, note: str) -> None:
        final_note = self._clip(self._first_line(note))
        if final_note:
            self._push_unique(self.state.completed_steps, f"completed: {final_note}")
        self.state.current_focus = "prepare the final answer"
        self.state.next_step = ""

    def build_brief(self) -> str:
        lines = ["[Execution Brief]"]
        lines.append(f"Goal: {self.state.goal or '(empty)'}")
        lines.append(f"Current Focus: {self.state.current_focus or '(unset)'}")
        if self.state.ranked_tools:
            lines.append(f"Ranked Tools: {', '.join(self.state.ranked_tools)}")
        if self.state.active_contract:
            lines.append(f"Active Contract: {self.state.active_contract}")
        if self.state.completed_steps:
            lines.append("Completed Steps:")
            lines.extend(f"- {item}" for item in self.state.completed_steps[-self.max_items :])
        if self.state.recent_observations:
            lines.append("Recent Observations:")
            lines.extend(
                f"- {item}" for item in self.state.recent_observations[-self.max_items :]
            )
        if self.state.teacher_guidance:
            lines.append(f"Teacher Guidance: {self.state.teacher_guidance}")
        if self.state.next_step:
            lines.append(f"Next Step: {self.state.next_step}")
        return "\n".join(lines)

    def compact_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if not messages:
            return []
        system = messages[0]
        non_system = messages[1:]
        if len(non_system) <= self.compress_trigger:
            return list(messages)

        older = non_system[:-self.keep_recent_messages]
        tail = non_system[-self.keep_recent_messages :]
        summary = self._summarize_history(older)
        compacted = [system]
        if summary:
            compacted.append(
                {
                    "role": "assistant",
                    "content": f"[Compressed Loop History]\n{summary}",
                }
            )
        compacted.extend(tail)
        return compacted

    def _summarize_history(self, messages: list[dict[str, str]]) -> str:
        items: list[str] = []
        for msg in messages:
            content = msg.get("content", "").strip()
            if not content:
                continue
            if msg.get("role") == "assistant":
                action_match = self._ACTION_RE.search(content)
                if action_match:
                    items.append(f"tool action: {self._clip(action_match.group(1), 120)}")
                    continue
                if "```tool_spec" in content.lower():
                    items.append("drafted a tool contract")
                    continue
            if msg.get("role") == "user" and content.startswith("Observation:"):
                items.append(
                    f"observation: {self._clip(self._first_line(content[12:].strip()), 140)}"
                )

        if not items:
            items.append("earlier loop turns were compressed to preserve context budget")
        deduped: list[str] = []
        for item in items:
            if item not in deduped:
                deduped.append(item)
        return "\n".join(f"- {item}" for item in deduped[-self.max_items :])

    def _push(self, target: list[str], value: str) -> None:
        if not value:
            return
        target.append(value)
        del target[:-self.max_items]

    def _push_unique(self, target: list[str], value: str) -> None:
        if not value:
            return
        if value in target:
            target.remove(value)
        target.append(value)
        del target[:-self.max_items]

    def _clip(self, text: str, limit: int | None = None) -> str:
        max_len = limit or self.text_limit
        clean = " ".join(text.split())
        if len(clean) <= max_len:
            return clean
        return clean[: max_len - 3].rstrip() + "..."

    @staticmethod
    def _first_line(text: str) -> str:
        return text.strip().splitlines()[0] if text.strip() else ""

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        return re.sub(r"```[\s\S]*?```", "", text).strip()
