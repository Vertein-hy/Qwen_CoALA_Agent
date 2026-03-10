from __future__ import annotations

from skills.validator import SkillValidator


def test_validator_accepts_simple_snake_case_function() -> None:
    validator = SkillValidator()
    result = validator.validate(
        """
def summarize_numbers(values):
    \"\"\"Return summary stats.\"\"\"
    return {"count": len(values), "sum": sum(values)}
        """
    )

    assert result.is_valid
    assert result.function_name == "summarize_numbers"
    assert result.errors == ()


def test_validator_rejects_dangerous_calls() -> None:
    validator = SkillValidator()
    result = validator.validate(
        """
def run_shell(cmd):
    import subprocess
    return subprocess.run(cmd, shell=True)
        """
    )

    assert not result.is_valid
    assert any("not allowed" in item for item in result.errors)


def test_validator_rejects_non_snake_case_name() -> None:
    validator = SkillValidator()
    result = validator.validate(
        """
def CamelCaseName(value):
    return value
        """
    )

    assert not result.is_valid
    assert any("snake_case" in item for item in result.errors)


def test_validator_strips_top_level_side_effects_but_keeps_required_imports() -> None:
    validator = SkillValidator()
    result = validator.validate(
        """
import math

def calc_lcm(a, b):
    \"\"\"Return least common multiple.\"\"\"
    if a == 0 or b == 0:
        return 0
    return abs(a * b) // math.gcd(a, b)

print(calc_lcm(12, 18))
        """
    )

    assert result.is_valid
    assert result.function_name == "calc_lcm"
    assert result.normalized_code.lstrip().startswith("def calc_lcm")
    assert "print(" not in result.normalized_code
    assert "import math" in result.normalized_code
