"""Tool execution module.

Design goals:
- High cohesion: tool management logic stays here.
- Low coupling: agent only depends on ToolExecutor interface.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from modules.document_summary import DocumentSummaryTool
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
        self.document_summary = DocumentSummaryTool(data_dir=self.data_dir)

        self._register_builtin_tools()
        self.load_internalized_skills()

    def _register_builtin_tools(self) -> None:
        self.registry.register("python_repl", self.python_repl)
        self.registry.register("write_file", self.write_file)
        self.registry.register("read_file", self.read_file)
        self.registry.register("extract_http_routes", self.extract_http_routes)
        self.registry.register("summarize_documents", self.summarize_documents)
        self.registry.register("summarize_documents_semantic", self.summarize_documents_semantic)

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
            "3. read_file: read a file by relative path; if input contains '|', only the filename part is used.",
            "4. extract_http_routes: scan a project path and return a Markdown summary of HTTP routes.",
            "5. summarize_documents: summarize one file or all supported documents in a folder.",
            "6. summarize_documents_semantic: build a second-stage global semantic summary from compressed document summaries.",
        ]

        custom_lines = []
        for name, func in self.registry.items():
            if name in {
                "python_repl",
                "write_file",
                "read_file",
                "extract_http_routes",
                "summarize_documents",
                "summarize_documents_semantic",
            }:
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

    def has_tool(self, tool_name: str) -> bool:
        return self.registry.has(tool_name)

    def python_repl(self, code: str) -> str:
        cleaned = self._normalize_python_input(self._strip_code_fence(code))
        output_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(output_buffer):
                exec(cleaned, self.python_state)
            output = output_buffer.getvalue().strip()
            if output:
                return output
            return "Execution success (no stdout). If you need a visible result, use print(...)."
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
        raw = name.strip()
        if not raw:
            return "File does not exist."
        if "|" in raw:
            raw = raw.split("|", 1)[0].strip()
        candidate = Path(raw)
        search_order = []
        if candidate.is_absolute():
            search_order.append(candidate)
        else:
            search_order.append(Path.cwd() / candidate)
            search_order.append(self.data_dir / candidate)
        for target in search_order:
            if target.exists() and target.is_file():
                return target.read_text(encoding="utf-8")
        return "File does not exist."

    def extract_http_routes(self, raw_input: str) -> str:
        project_root = self._resolve_project_root(raw_input)
        if project_root is None:
            return "Project path does not exist."

        route_rows: list[dict[str, str]] = []
        for py_file in sorted(project_root.rglob("*.py")):
            if any(part.startswith(".") for part in py_file.parts):
                continue
            if "__pycache__" in py_file.parts:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                route_rows.append(
                    {
                        "file": str(py_file.relative_to(project_root)),
                        "method": "ERROR",
                        "path": "",
                        "handler": f"read_failed: {exc}",
                    }
                )
                continue
            route_rows.extend(self._extract_routes_from_source(content, py_file, project_root))

        if not route_rows:
            return "No HTTP API routes found."

        route_rows = [row for row in route_rows if row["method"] != "ERROR"]
        if not route_rows:
            return "No HTTP API routes found."

        lines = [
            "# HTTP API Routes",
            "",
            "| Method | Path | Handler | File |",
            "|---|---|---|---|",
        ]
        for row in route_rows:
            lines.append(
                f"| {row['method']} | {row['path']} | {row['handler']} | {row['file']} |"
            )
        lines.append("")
        lines.append(f"Total routes: {len(route_rows)}")
        return "\n".join(lines)

    def summarize_documents(self, raw_input: str) -> str:
        return self.document_summary.summarize(raw_input)

    def summarize_documents_semantic(self, raw_input: str) -> str:
        return self.document_summary.summarize_semantic(raw_input)

    @staticmethod
    def _strip_code_fence(code: str) -> str:
        text = code.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        if (
            (text.startswith("'''") and text.endswith("'''"))
            or (text.startswith('"""') and text.endswith('"""'))
        ):
            text = text[3:-3]
        return text.strip()

    @staticmethod
    def _normalize_python_input(code: str) -> str:
        text = code.strip()
        # Small models often emit single-line Action Input with escaped control chars.
        # Decode only outside quoted strings to avoid breaking literals like '\\n'.
        if "\n" not in text and ("\\" in text):
            text = ToolBox._decode_escaped_controls_outside_strings(text)
        # Remove stray role leakage that should never be part of runnable code.
        text = re.split(r"\n(?:assistant:|user:|Action:)", text, maxsplit=1)[0]
        return text.strip()

    @staticmethod
    def _decode_escaped_controls_outside_strings(text: str) -> str:
        out: list[str] = []
        in_single = False
        in_double = False
        escape = False
        i = 0
        while i < len(text):
            ch = text[i]
            if escape:
                out.append(ch)
                escape = False
                i += 1
                continue
            if ch == "\\":
                if i + 1 < len(text):
                    nxt = text[i + 1]
                    if not in_single and not in_double and nxt == "n":
                        out.append("\n")
                        i += 2
                        continue
                    if not in_single and not in_double and nxt == "t":
                        out.append("\t")
                        i += 2
                        continue
                out.append(ch)
                escape = True
                i += 1
                continue
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            out.append(ch)
            i += 1
        return "".join(out)

    def _resolve_project_root(self, raw_input: str) -> Path | None:
        cleaned = raw_input.strip().strip("'").strip('"')
        if not cleaned:
            cleaned = "."
        candidate = Path(cleaned)
        search_order = []
        if candidate.is_absolute():
            search_order.append(candidate)
        else:
            search_order.append(Path.cwd() / candidate)
            search_order.append(self.data_dir / candidate)
        for target in search_order:
            if target.exists() and target.is_dir():
                return target
        return None

    @staticmethod
    def _extract_routes_from_source(content: str, py_file: Path, project_root: Path) -> list[dict[str, str]]:
        relative_path = str(py_file.relative_to(project_root))
        rows: list[dict[str, str]] = []
        patterns = (
            (
                re.compile(
                    r"@(?:app|router|bp|blueprint)\.(get|post|put|delete|patch|options|head)\(\s*[\"']([^\"']+)[\"']"
                ),
                None,
            ),
            (
                re.compile(
                    r"@(?:app|router|bp|blueprint)\.route\(\s*[\"']([^\"']+)[\"']\s*,\s*methods\s*=\s*\[([^\]]+)\]"
                ),
                "methods_list",
            ),
        )

        lines = content.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            for pattern, mode in patterns:
                match = pattern.search(stripped)
                if not match:
                    continue
                handler = ToolBox._infer_next_function_name(lines, index)
                if mode == "methods_list":
                    path = match.group(1)
                    methods = re.findall(r"[\"']([A-Za-z]+)[\"']", match.group(2))
                    for method in methods or ["GET"]:
                        rows.append(
                            {
                                "file": relative_path,
                                "method": method.upper(),
                                "path": path,
                                "handler": handler,
                            }
                        )
                else:
                    rows.append(
                        {
                            "file": relative_path,
                            "method": match.group(1).upper(),
                            "path": match.group(2),
                            "handler": handler,
                        }
                    )
        return rows

    @staticmethod
    def _infer_next_function_name(lines: list[str], start_index: int) -> str:
        for candidate in lines[start_index + 1 : start_index + 6]:
            match = re.match(r"\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", candidate)
            if match:
                return match.group(1)
        return "(unknown)"
