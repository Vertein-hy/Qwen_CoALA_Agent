from __future__ import annotations

from pathlib import Path

from modules.tools import ToolBox


def test_python_repl_executes_triple_quoted_action_input() -> None:
    tools = ToolBox(data_dir="tests_runtime/tools_case")

    output = tools.python_repl(
        "'''\n"
        "value = 21 * 2\n"
        "print(value)\n"
        "'''"
    )

    assert output == "42"


def test_python_repl_executes_fenced_code_block() -> None:
    tools = ToolBox(data_dir="tests_runtime/tools_case")

    output = tools.python_repl(
        "```python\n"
        "print('ok')\n"
        "```"
    )

    assert output == "ok"


def test_python_repl_no_stdout_returns_actionable_hint() -> None:
    tools = ToolBox(data_dir="tests_runtime/tools_case")

    output = tools.python_repl("value = 7")

    assert "Execution success (no stdout)." in output
    assert "print(...)" in output


def test_read_file_accepts_pipe_suffix_and_project_relative_path(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    current = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        output = tools.read_file("main.py|content")
    finally:
        os.chdir(current)

    assert "print('hello')" in output
