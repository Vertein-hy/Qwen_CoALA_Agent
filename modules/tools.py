"""Tool execution module.

Design goals:
- High cohesion: tool management logic stays here.
- Low coupling: agent only depends on ToolExecutor interface.
"""

from __future__ import annotations

import contextlib
import inspect
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from skills.runtime_loader import SkillPluginLoader


ToolFunc = Callable[[str], str]


@dataclass
class ToolRegistry:
    """Registry that stores tool handlers by name."""

    _tools: dict[str, ToolFunc] = field(default_factory=dict)

    def register(self, name: str, func: ToolFunc) -> None:
        self._tools[name] = func

    def has(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolFunc:
        return self._tools[name]

    def items(self):
        return self._tools.items()


class ToolBox:
    """Built-in tools + dynamically loaded internalized skills."""

    def __init__(self, data_dir: str = "data", skills_file: str = "skills/internalized/custom_skills.py"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.skills_file = Path(skills_file)
        self.python_state: dict = {}
        self.registry = ToolRegistry()

        self._register_builtin_tools()
        self.load_internalized_skills()

    def _register_builtin_tools(self) -> None:
        self.registry.register("python_repl", self.python_repl)
        self.registry.register("write_file", self.write_file)
        self.registry.register("read_file", self.read_file)

    def load_internalized_skills(self) -> None:
        """Load callables from skills/internalized/custom_skills.py.

        Only user-defined public callables are imported as tools.
        """
        index_file = self.skills_file.with_name("index.json")
        loader = SkillPluginLoader(
            skills_file=self.skills_file,
            index_file=index_file,
        )
        for attr_name, attr in loader.load().items():
            # Wrap arbitrary function signatures into string-input tools.
            self.registry.register(attr_name, self._wrap_skill(attr_name, attr))

    def _wrap_skill(self, name: str, func: Callable) -> ToolFunc:
        def _runner(raw_input: str) -> str:
            expression = raw_input.strip()
            if not expression:
                result = func()
                return "" if result is None else str(result)

            # Execute skill in python sandbox state to support complex args.
            local_scope = {name: func}
            script = f"_tool_out = {name}({expression})"
            try:
                exec(script, self.python_state, local_scope)
                out = local_scope.get("_tool_out")
                return "" if out is None else str(out)
            except Exception as exc:  # noqa: BLE001
                return f"Skill error: {exc}"

        return _runner

    def get_tool_desc(self) -> str:
        lines = [
            "[Built-in Tools]",
            "1. python_repl: execute Python code safely in session state.",
            "2. write_file: write a file, format is 'filename|content'.",
            "3. read_file: read a file by name from data directory.",
        ]

        custom_lines = []
        for name, func in self.registry.items():
            if name in {"python_repl", "write_file", "read_file"}:
                continue
            try:
                sig = str(inspect.signature(func))
            except Exception:  # noqa: BLE001
                sig = "(input: str)"
            custom_lines.append(f"- {name}{sig}")

        if custom_lines:
            lines.append("\n[Internalized Skills]")
            lines.extend(custom_lines)

        return "\n".join(lines)

    def execute(self, tool_name: str, tool_input: str) -> str:
        if not self.registry.has(tool_name):
            return f"Tool not found: '{tool_name}'"

        try:
            return self.registry.get(tool_name)(tool_input)
        except Exception as exc:  # noqa: BLE001
            return f"Tool execution error: {exc}"

    def python_repl(self, code: str) -> str:
        cleaned = self._strip_code_fence(code)
        output_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(cleaned, self.python_state)
            output = output_buffer.getvalue().strip()
            return output if output else "Execution success (no stdout)."
        except Exception as exc:  # noqa: BLE001
            return f"Python Error: {exc}"

    def write_file(self, args: str) -> str:
        if "|" not in args:
            return "Invalid format. Use 'filename|content'."

        filename, content = args.split("|", 1)
        target = self.data_dir / filename.strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File written: {target}"

    def read_file(self, name: str) -> str:
        target = self.data_dir / name.strip()
        if not target.exists():
            return "File does not exist."
        return target.read_text(encoding="utf-8")

    @staticmethod
    def _strip_code_fence(code: str) -> str:
        text = code.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        return text.strip()
