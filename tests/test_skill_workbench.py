from __future__ import annotations

from skills.tool_contracts import ToolIOField, ToolSpec
from skills.workbench import SkillWorkbench


def _sample_spec() -> ToolSpec:
    return ToolSpec(
        name="draft_sum_tool",
        purpose="Return the sum from 1 to n.",
        inputs=(ToolIOField(name="n", type_name="int", required=True),),
        outputs=(ToolIOField(name="result", type_name="int"),),
    )


def test_skill_workbench_accepts_matching_code() -> None:
    workbench = SkillWorkbench()

    result = workbench.evaluate(
        function_code="""
def draft_sum_tool(n):
    \"\"\"Return the sum from 1 to n.\"\"\"
    return sum(range(1, n + 1))
        """,
        spec=_sample_spec(),
    )

    assert result.is_valid is True
    assert result.function_name == "draft_sum_tool"


def test_skill_workbench_rejects_mismatched_function_name() -> None:
    workbench = SkillWorkbench()

    result = workbench.evaluate(
        function_code="""
def wrong_name(n):
    return sum(range(1, n + 1))
        """,
        spec=_sample_spec(),
    )

    assert result.is_valid is False
    assert "does not match tool contract name" in result.errors[0]


def test_skill_workbench_rejects_signature_mismatch() -> None:
    workbench = SkillWorkbench()

    result = workbench.evaluate(
        function_code="""
def draft_sum_tool(x, y):
    return x + y
        """,
        spec=_sample_spec(),
    )

    assert result.is_valid is False
    assert "signature does not match required contract inputs" in result.errors[0].lower()
