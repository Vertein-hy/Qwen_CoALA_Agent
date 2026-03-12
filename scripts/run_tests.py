"""Canonical pytest entrypoint with stable suite names."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SUITES: dict[str, list[str]] = {
    "all": ["tests"],
    "agent": ["tests/test_agent_trace.py", "tests/test_react_parser.py", "tests/test_scorer.py"],
    "skills": [
        "tests/test_skill_manager.py",
        "tests/test_skill_runtime_loader.py",
        "tests/test_skill_selector.py",
        "tests/test_skill_validator.py",
        "tests/test_skill_event_logger.py",
        "tests/test_tool_lifecycle.py",
    ],
    "memory": ["tests/test_memory.py"],
    "llm": ["tests/test_llm.py", "tests/test_openai_compat_fallback.py", "tests/test_router.py"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES),
        default="all",
        help="Named test suite to run.",
    )
    args, pytest_args = parser.parse_known_args()

    targets = SUITES[args.suite]
    cmd = [sys.executable, "-m", "pytest", "-q", *targets, *pytest_args]
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
