"""Short-term dialogue memory."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkingMemory:
    """Conversation history buffer used as model context."""

    max_messages: int = 30
    history: list[dict[str, str]] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        if len(self.history) > self.max_messages:
            # Keep system prompt and latest turns.
            system = [m for m in self.history[:1] if m.get("role") == "system"]
            tail = self.history[-(self.max_messages - len(system)) :]
            self.history = system + tail

    def get_context(self) -> list[dict[str, str]]:
        return list(self.history)

    def replace_system_prompt(self, content: str) -> None:
        if self.history and self.history[0].get("role") == "system":
            self.history[0] = {"role": "system", "content": content}
            return
        self.history.insert(0, {"role": "system", "content": content})

    def clear(self) -> None:
        self.history.clear()
