from __future__ import annotations

import json
from pathlib import Path

from rl.contracts import DecisionAction, DecisionSample, DecisionState
from rl.decision_dataset import export_trace_dataset, load_jsonl, sample_from_trace
from rl.policy import LinearDecisionPolicy
from rl.runtime_router import RLRuntimeRouter


def test_sample_from_trace_prefers_direct_tool_on_success() -> None:
    trace = {
        "trace_id": "tr_success",
        "user_input": "请从当前项目代码中提取所有 HTTP API 路由，并输出 markdown 摘要。",
        "status": "success",
        "route": "deterministic_skill_router",
        "model_name": "small",
        "skill_candidates": [{"name": "extract_http_routes", "score": 4.2}],
        "tool_matches": [{"name": "extract_http_routes", "score": 5.1}],
        "steps": [
            {"kind": "policy", "content": "action=direct_tool", "metadata": {}},
            {"kind": "direct_route", "content": "extract_http_routes({})", "metadata": {}},
            {"kind": "action", "content": "extract_http_routes({})", "metadata": {}},
            {"kind": "observation", "content": "# HTTP API Routes", "metadata": {}},
            {"kind": "final", "content": "# HTTP API Routes", "metadata": {}},
        ],
    }

    sample = sample_from_trace(trace)

    assert sample.action is DecisionAction.DIRECT_TOOL
    assert sample.reward > 1.0
    assert sample.state.tool_match_count == 1
    assert sample.state.top_tool_score == 5.1


def test_sample_from_trace_marks_repeated_tool_error() -> None:
    trace = {
        "trace_id": "tr_timeout",
        "user_input": "请扫描项目 API 路由",
        "status": "timeout",
        "route": "timeout",
        "model_name": "small",
        "skill_candidates": [],
        "tool_matches": [],
        "steps": [
            {"kind": "tool_spec", "content": "{}", "metadata": {}},
            {"kind": "observation", "content": "Python Error: invalid syntax", "metadata": {}},
            {"kind": "observation", "content": "File does not exist.", "metadata": {}},
        ],
    }

    sample = sample_from_trace(trace)

    assert sample.state.has_tool_spec is True
    assert sample.state.repeated_tool_error is True
    assert sample.reward < 0.0


def test_linear_policy_prefers_direct_tool_for_route_extraction() -> None:
    policy = LinearDecisionPolicy()
    state = DecisionState(
        user_input="请从当前项目代码中提取所有 HTTP API 路由，并输出 markdown 摘要。",
        skill_candidate_count=1,
        tool_match_count=1,
        top_skill_score=4.0,
        top_tool_score=5.0,
        current_step_count=0,
    )

    suggestion = policy.suggest(state)

    assert suggestion.action is DecisionAction.DIRECT_TOOL
    assert suggestion.confidence > 0


def test_linear_policy_updates_toward_sample_action() -> None:
    policy = LinearDecisionPolicy()
    state = DecisionState(
        user_input="请定义新的 Tool Spec 来处理项目接口",
        has_tool_spec=True,
        tool_match_count=0,
        top_tool_score=0.0,
    )
    before = policy.suggest(state).scores[DecisionAction.BUILD_TOOL.value]
    sample = DecisionSample(
        trace_id="tr_build",
        state=state,
        action=DecisionAction.BUILD_TOOL,
        reward=1.0,
        outcome="success",
    )

    policy.update_from_samples([sample], learning_rate=0.1)
    after = policy.suggest(state).scores[DecisionAction.BUILD_TOOL.value]

    assert after > before


def test_runtime_router_builds_state_and_suggests() -> None:
    router = RLRuntimeRouter()
    suggestion = router.suggest(
        user_input="请输出 HTTP API 路由摘要",
        skill_candidates=[{"name": "extract_http_routes", "score": 4.0}],
        tool_matches=[{"name": "extract_http_routes", "score": 5.2}],
        steps=[{"kind": "observation", "content": "done"}],
        route_hint="pre_loop",
    )

    assert suggestion.action is DecisionAction.DIRECT_TOOL


def test_export_trace_dataset_writes_jsonl(tmp_path: Path) -> None:
    traces = [
        {
            "trace_id": "tr_export",
            "user_input": "请输出 HTTP API 路由摘要",
            "status": "success",
            "route": "deterministic_skill_router",
            "model_name": "small",
            "skill_candidates": [],
            "tool_matches": [{"name": "extract_http_routes", "score": 5.0}],
            "steps": [{"kind": "direct_route", "content": "extract_http_routes({})", "metadata": {}}],
        }
    ]
    output_path = tmp_path / "rl_samples.jsonl"

    count = export_trace_dataset(traces, output_path)

    assert count == 1
    row = json.loads(output_path.read_text(encoding="utf-8").strip())
    assert row["trace_id"] == "tr_export"
    assert row["action"] == DecisionAction.DIRECT_TOOL.value


def test_load_jsonl_tolerates_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "trace_samples.jsonl"
    path.write_text('{"trace_id":"tr_bom"}\n', encoding="utf-8-sig")

    rows = load_jsonl(path)

    assert rows == [{"trace_id": "tr_bom"}]
