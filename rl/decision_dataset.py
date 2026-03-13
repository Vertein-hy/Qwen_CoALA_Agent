"""Offline dataset extraction for decision-layer reinforcement learning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from rl.contracts import DecisionAction, DecisionSample, DecisionState


def build_state_from_trace(trace: dict) -> DecisionState:
    steps = trace.get("steps", []) or []
    tool_matches = trace.get("tool_matches", []) or []
    skill_candidates = trace.get("skill_candidates", []) or []

    top_tool_score = 0.0
    if tool_matches:
        top_tool_score = float(tool_matches[0].get("score", 0.0) or 0.0)

    top_skill_score = 0.0
    if skill_candidates:
        top_skill_score = float(skill_candidates[0].get("score", 0.0) or 0.0)

    return DecisionState(
        user_input=str(trace.get("user_input", "")),
        skill_candidate_count=len(skill_candidates),
        tool_match_count=len(tool_matches),
        top_skill_score=top_skill_score,
        top_tool_score=top_tool_score,
        has_tool_spec=any(step.get("kind") == "tool_spec" for step in steps),
        repeated_tool_error=_trace_has_repeated_tool_error(steps),
        current_step_count=len(steps),
        route_hint=str(trace.get("route", "")),
        metadata={
            "status": trace.get("status", ""),
            "model_name": trace.get("model_name", ""),
        },
    )


def infer_action_from_trace(trace: dict) -> DecisionAction:
    steps = trace.get("steps", []) or []
    kinds = [str(step.get("kind", "")) for step in steps]

    if "direct_route" in kinds:
        return DecisionAction.DIRECT_TOOL
    if "tool_spec" in kinds:
        if any("teacher" in str(step.get("content", "")).lower() for step in steps):
            return DecisionAction.ASK_TEACHER
        return DecisionAction.BUILD_TOOL
    if str(trace.get("status", "")) == "success":
        return DecisionAction.FINALIZE
    return DecisionAction.CONTINUE


def reward_from_trace(trace: dict) -> float:
    status = str(trace.get("status", "")).lower()
    steps = trace.get("steps", []) or []
    reward = 0.0

    if status == "success":
        reward += 1.0
    elif status == "timeout":
        reward -= 0.5
    elif status == "fallback":
        reward -= 0.25

    if any(step.get("kind") == "direct_route" for step in steps):
        reward += 0.5
    if any(step.get("kind") == "tool_spec" for step in steps):
        reward -= 0.1
    if _trace_has_repeated_tool_error(steps):
        reward -= 0.2

    reward -= min(0.3, max(0, len(steps) - 4) * 0.05)
    return round(reward, 4)


def sample_from_trace(trace: dict) -> DecisionSample:
    return DecisionSample(
        trace_id=str(trace.get("trace_id", "")),
        state=build_state_from_trace(trace),
        action=infer_action_from_trace(trace),
        reward=reward_from_trace(trace),
        outcome=str(trace.get("status", "")),
        metadata={
            "route": trace.get("route", ""),
            "model_name": trace.get("model_name", ""),
        },
    )


def export_trace_dataset(traces: Iterable[dict], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for trace in traces:
            sample = sample_from_trace(trace)
            handle.write(json.dumps(sample.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    return count


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
    return rows


def _trace_has_repeated_tool_error(steps: list[dict]) -> bool:
    tool_error_count = 0
    for step in steps:
        if step.get("kind") != "observation":
            continue
        content = str(step.get("content", "")).lower()
        if "python error" in content or "tool not found" in content or "file does not exist" in content:
            tool_error_count += 1
    return tool_error_count >= 2
