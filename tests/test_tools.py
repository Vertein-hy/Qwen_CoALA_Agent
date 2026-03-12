from __future__ import annotations

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
