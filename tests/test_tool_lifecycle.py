from __future__ import annotations

from skills.tool_builder import ToolBuilderPlanner
from skills.tool_contracts import (
    HelpRequestKind,
    ProjectToolContext,
    ToolBuildRequest,
    ToolExecutionRecord,
    ToolFailureRecord,
    ToolIOField,
    ToolKnowledgeBase,
    ToolSpec,
)
from skills.tool_discovery import ToolDiscoveryEngine
from skills.tool_escalation import TeacherEscalationPlanner
from skills.tool_promotion import ToolPromotionPolicy
from skills.tool_registry import ToolRegistry


def _sample_spec() -> ToolSpec:
    return ToolSpec(
        name="extract_api_summary",
        purpose="Extract API definitions from a repository and summarize them.",
        inputs=(
            ToolIOField(name="repo_path", type_name="path"),
            ToolIOField(name="output_format", type_name="string", required=False),
        ),
        outputs=(
            ToolIOField(name="api_list", type_name="json"),
            ToolIOField(name="summary_md", type_name="markdown"),
        ),
        failure_modes=("repo_not_found", "definition_not_found"),
        examples=("repo_path=/workspace/app",),
        dependencies=("python", "ripgrep"),
        tags=("api", "summary", "repo"),
    )


def test_tool_discovery_prefers_matching_contract() -> None:
    context = ProjectToolContext(
        project_id="proj-1",
        task_summary="extract api summary from repo",
        available_inputs=("repo_path",),
        desired_outputs=("api_list", "summary_md"),
        environment_facts=("python installed", "ripgrep installed"),
    )
    kb = ToolKnowledgeBase(specs=[_sample_spec()])
    engine = ToolDiscoveryEngine(knowledge_base=kb)

    results = engine.recommend(context, top_k=3)

    assert len(results) == 1
    assert results[0].spec.name == "extract_api_summary"
    assert results[0].breakdown.total_score > 0


def test_tool_discovery_supports_cjk_overlap_tokens() -> None:
    context = ProjectToolContext(
        project_id="proj-http",
        task_summary="请提取当前项目中的 HTTP API 路由并输出 markdown 摘要",
        available_inputs=("user_request", "memory_context"),
        desired_outputs=("final_answer",),
        environment_facts=("python_available", "local_toolbox_available"),
    )
    spec = ToolSpec(
        name="extract_http_routes",
        purpose="提取当前项目中的 HTTP API 路由并输出 Markdown 摘要。",
        inputs=(ToolIOField(name="repo_path", type_name="string", required=False),),
        outputs=(ToolIOField(name="markdown_summary", type_name="string"),),
        tags=("http", "api", "route", "markdown", "deterministic_builtin"),
    )
    engine = ToolDiscoveryEngine(knowledge_base=ToolKnowledgeBase(specs=[spec]))

    results = engine.recommend(context, top_k=1)

    assert len(results) == 1
    assert results[0].spec.name == "extract_http_routes"
    assert results[0].breakdown.goal_match >= 3.0


def test_tool_builder_requires_contract_fields() -> None:
    planner = ToolBuilderPlanner()
    readiness = planner.assess_readiness(
        ToolSpec(
            name="draft_tool",
            purpose="",
            inputs=(),
            outputs=(),
        )
    )

    assert readiness.ready is False
    assert "purpose" in readiness.missing_items
    assert "inputs" in readiness.missing_items
    assert "outputs" in readiness.missing_items


def test_teacher_request_is_structured() -> None:
    planner = TeacherEscalationPlanner()
    context = ProjectToolContext(
        project_id="proj-1",
        task_summary="need a tool to summarize repository apis",
        constraints=("offline", "linux ipc"),
    )
    request = planner.create_request(
        kind=HelpRequestKind.PROPOSE_NEW_TOOL,
        context=context,
        current_spec=None,
        failures=[
            ToolFailureRecord(stage="discovery", reason="no suitable tool found"),
            ToolFailureRecord(stage="build", reason="contract missing output field"),
        ],
    )

    assert request.kind == HelpRequestKind.PROPOSE_NEW_TOOL
    assert request.goal == context.task_summary
    assert len(request.failures) == 2
    assert "new tool contract" in request.requested_output.lower()


def test_promotion_policy_rewards_cross_project_success() -> None:
    policy = ToolPromotionPolicy()
    decision = policy.decide(
        [
            ToolExecutionRecord(
                tool_name="extract_api_summary",
                project_id="proj-1",
                success=True,
                matched_contract=True,
                latency_ms=200,
                reused_existing_tool=True,
            ),
            ToolExecutionRecord(
                tool_name="extract_api_summary",
                project_id="proj-2",
                success=True,
                matched_contract=True,
                latency_ms=220,
                reused_existing_tool=True,
            ),
        ]
    )

    assert decision.should_promote is True
    assert decision.tier.value in {"project", "global"}


def test_build_outline_mentions_contract_io() -> None:
    planner = ToolBuilderPlanner()
    outline = planner.build_outline(
        ToolBuildRequest(
            context=ProjectToolContext(
                project_id="proj-1",
                task_summary="extract api summary from repo",
            ),
            spec=_sample_spec(),
        )
    )

    assert "repo_path:path" in outline
    assert "api_list:json" in outline


def test_tool_registry_persists_specs_and_promotions(tmp_path) -> None:
    registry = ToolRegistry(index_file=tmp_path / "tool_registry.json")
    spec = _sample_spec()

    registry.upsert_spec(
        spec=spec,
        project_id="proj-1",
        source="summarize repo apis",
        origin="teacher",
    )
    registry.add_execution(
        ToolExecutionRecord(
            tool_name=spec.name,
            project_id="proj-1",
            success=True,
            matched_contract=True,
            latency_ms=120,
        )
    )
    registry.add_execution(
        ToolExecutionRecord(
            tool_name=spec.name,
            project_id="proj-2",
            success=True,
            matched_contract=True,
            latency_ms=140,
            reused_existing_tool=True,
        )
    )

    policy = ToolPromotionPolicy()
    decision = policy.decide(registry.executions_for(spec.name))
    updated = registry.apply_promotion(spec.name, decision)

    assert updated is not None
    assert updated.name == spec.name
    assert updated.tier.value in {"project", "global"}
    assert registry.get_record(spec.name) is not None
