from __future__ import annotations

import json
from pathlib import Path
import zipfile

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


def test_python_repl_keeps_escaped_newline_inside_string_literal() -> None:
    tools = ToolBox(data_dir="tests_runtime/tools_case")

    output = tools.python_repl(r"print('\n'.join(['a', 'b']))")

    assert output == "a\nb"


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


def test_summarize_documents_returns_single_text_file_summary(tmp_path: Path) -> None:
    target = tmp_path / "notes.md"
    target.write_text("# Weekly Plan\n- finish api design\n- review tests\n", encoding="utf-8")
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.summarize_documents(str(target))

    assert "# Document Summary" in output
    assert "- File: `notes.md`" in output
    assert "Weekly Plan" in output
    assert "finish api design" in output


def test_summarize_documents_returns_directory_summary(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.md").write_text("# Readme\nProject overview.\n", encoding="utf-8")
    (docs_dir / "report.txt").write_text("Quality Report\nstatus: stable\n", encoding="utf-8")
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.summarize_documents(str(docs_dir))

    assert "# Directory Document Summary" in output
    assert "readme.md" in output
    assert "report.txt" in output
    assert "Files summarized: 2" in output


def test_summarize_documents_supports_global_scope(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("# API Notes\nroute summary\n", encoding="utf-8")
    (docs_dir / "b.txt").write_text("Budget review\nstatus: approved\n", encoding="utf-8")
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.summarize_documents(
        json.dumps({"path": str(docs_dir), "scope": "global"}, ensure_ascii=False)
    )

    assert "# Global Document Summary" in output
    assert "## Overview" in output
    assert "Files summarized: 2" in output


def test_summarize_documents_semantic_returns_theme_summary(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "api.md").write_text("# API Review\nHTTP route coverage\n", encoding="utf-8")
    (docs_dir / "ops.txt").write_text("Service status stable\nAPI checks passed\n", encoding="utf-8")
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.summarize_documents_semantic(str(docs_dir))

    assert "# Semantic Document Summary" in output
    assert "Themes:" in output
    assert "Priority Files" in output


def test_summarize_documents_reads_docx_file(tmp_path: Path) -> None:
    target = tmp_path / "report.docx"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                "<w:p><w:r><w:t>Project Summary</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Milestone completed.</w:t></w:r></w:p>"
                "</w:body></w:document>"
            ),
        )
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.summarize_documents(str(target))

    assert "Project Summary" in output
    assert "Milestone completed." in output


def test_summarize_documents_reads_xlsx_file(tmp_path: Path) -> None:
    target = tmp_path / "budget.xlsx"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '<Override PartName="/xl/sharedStrings.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                "</Types>"
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Summary" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>"
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<si><t>Item</t></si><si><t>Budget</t></si><si><t>Model</t></si><si><t>1200</t></si>"
                "</sst>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>"
                '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>'
                "</sheetData></worksheet>"
            ),
        )
    tools = ToolBox(data_dir=str(tmp_path / "data"))

    output = tools.summarize_documents(str(target))

    assert "[Sheet] Summary" in output
    assert "Item | Budget" in output
    assert "Model | 1200" in output
