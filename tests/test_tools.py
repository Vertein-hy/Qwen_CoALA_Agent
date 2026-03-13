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


def test_python_repl_decodes_escaped_newlines() -> None:
    tools = ToolBox(data_dir="tests_runtime/tools_case")

    output = tools.python_repl("import os;\\nprint('ok')")

    assert output == "ok"


def test_extract_http_routes_returns_markdown_summary(tmp_path: Path) -> None:
    app_file = tmp_path / "app.py"
    app_file.write_text(
        "\n".join(
            [
                "from flask import Flask",
                "app = Flask(__name__)",
                "",
                "@app.get('/users')",
                "def list_users():",
                "    return []",
                "",
                "@app.route('/users/<int:user_id>', methods=['GET', 'DELETE'])",
                "def user_detail(user_id):",
                "    return {}",
            ]
        ),
        encoding="utf-8",
    )
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.extract_http_routes(str(tmp_path))

    assert "# HTTP API Routes" in output
    assert "| GET | /users | list_users | app.py |" in output
    assert "| GET | /users/<int:user_id> | user_detail | app.py |" in output
    assert "| DELETE | /users/<int:user_id> | user_detail | app.py |" in output
