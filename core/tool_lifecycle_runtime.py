"""Runtime helpers for tool discovery, contract handling, and promotion."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from config.settings import AppConfig
from core.context_compactor import LoopContextCompactor
from core.llm_interface import LLMInterface
from core.react_parser import ReActParser
from skills.event_logger import SkillEventLogger
from skills.manager import SkillManager
from skills.selector import SkillSelector
from skills.runtime_loader import SkillPluginLoader
from skills.tool_builder import ToolBuilderPlanner
from skills.tool_contracts import (
    HelpRequestKind,
    PromotionDecision,
    PromotionTier,
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
from skills.tool_parser import ToolLifecycleParser
from skills.tool_promotion import ToolPromotionPolicy
from skills.tool_registry import ToolRegistry
from skills.workbench import SkillWorkbench


class ToolLifecycleRuntime:
    """Encapsulate the mutable tool-contract lifecycle for the agent."""

    def __init__(
        self,
        *,
        config: AppConfig,
        llm: LLMInterface,
        skill_manager: SkillManager,
        skill_selector: SkillSelector,
        skill_event_logger: SkillEventLogger,
        tool_registry: ToolRegistry,
        tool_promotion: ToolPromotionPolicy,
        tool_builder: ToolBuilderPlanner,
        teacher_escalation: TeacherEscalationPlanner,
    ) -> None:
        self.config = config
        self.llm = llm
        self.skill_manager = skill_manager
        self.skill_selector = skill_selector
        self.skill_event_logger = skill_event_logger
        self.tool_registry = tool_registry
        self.tool_promotion = tool_promotion
        self.tool_builder = tool_builder
        self.teacher_escalation = teacher_escalation
        self.skill_workbench = SkillWorkbench(self.skill_manager.validator)

    def build_project_tool_context(self, user_input: str) -> ProjectToolContext:
        project_id = self.config.agent.project_id.strip() or Path.cwd().name or "active-session"
        return ProjectToolContext(
            project_id=project_id,
            task_summary=user_input.strip(),
            available_inputs=("user_request", "memory_context"),
            desired_outputs=("final_answer",),
            constraints=(
                "prefer_reuse_before_build",
                "contract_first_before_code",
                "structured_escalation_only_when_blocked",
            ),
            environment_facts=("python_available", "local_toolbox_available"),
            existing_tools=tuple(self.skill_manager.list_skills()),
        )

    def build_tool_knowledge_base(self) -> ToolKnowledgeBase:
        specs: list[ToolSpec] = []
        seen: set[str] = set()
        builtin_specs = (
            ToolSpec(
                name="extract_http_routes",
                purpose="提取当前项目中的 HTTP API 路由并输出 Markdown 摘要。",
                inputs=(
                    ToolIOField(
                        name="repo_path",
                        type_name="string",
                        required=False,
                        description="Project root path, default to current workspace.",
                    ),
                ),
                outputs=(
                    ToolIOField(name="markdown_summary", type_name="string"),
                ),
                examples=("extract routes from current project",),
                tags=("http", "api", "route", "markdown", "deterministic_builtin"),
            ),
            ToolSpec(
                name="summarize_documents",
                purpose="Read one document or a folder of documents and return deterministic summaries for text, PDF, DOCX, and XLSX files.",
                inputs=(
                    ToolIOField(
                        name="path",
                        type_name="string",
                        required=False,
                        description="File path or folder path. Defaults to current workspace.",
                    ),
                ),
                outputs=(ToolIOField(name="markdown_summary", type_name="string"),),
                examples=(
                    "summarize documents in current project",
                    "summarize ./docs",
                    '{"path":"./docs","scope":"file","file_path":"report.docx"}',
                ),
                tags=("document", "summary", "pdf", "docx", "xlsx", "folder", "文档", "摘要", "目录", "整体", "deterministic_builtin"),
            ),
            ToolSpec(
                name="summarize_documents_semantic",
                purpose="Build a second-stage global summary over compressed document summaries and highlight dominant themes.",
                inputs=(
                    ToolIOField(
                        name="path",
                        type_name="string",
                        required=False,
                        description="File path or folder path. Defaults to current workspace.",
                    ),
                ),
                outputs=(ToolIOField(name="semantic_summary", type_name="string"),),
                examples=(
                    "semantic summary for current project documents",
                    '{"path":"./docs","scope":"global"}',
                ),
                tags=("document", "summary", "semantic", "global", "文档", "主题", "整体", "摘要", "全局", "deterministic_builtin"),
            ),
        )
        for spec in builtin_specs:
            specs.append(spec)
            seen.add(spec.name)
        runtime_skills = SkillPluginLoader(
            skills_file=self.skill_manager.skill_file,
            index_file=self.skill_manager.index_file,
        ).load()
        for record in self.skill_manager.catalog.list_records():
            if not record.enabled:
                continue
            runtime_func = runtime_skills.get(record.name)
            specs.append(
                ToolSpec(
                    name=record.name,
                    purpose=self._infer_skill_purpose(record.name, record.source, runtime_func),
                    inputs=self._infer_skill_inputs(runtime_func),
                    outputs=self._infer_skill_outputs(runtime_func),
                    examples=(record.source.strip(),) if record.source.strip() else (),
                    tags=("internalized_skill",),
                )
            )
            seen.add(record.name)
        for record in self.tool_registry.list_records():
            if not record.enabled or record.name in seen:
                continue
            specs.append(record.spec)
            seen.add(record.name)
        return ToolKnowledgeBase(specs=specs)

    @staticmethod
    def _infer_skill_purpose(name: str, source: str, runtime_func: object | None) -> str:
        if callable(runtime_func):
            doc = inspect.getdoc(runtime_func) or ""
            if doc.strip():
                return doc.strip()
        return source.strip() or f"Reusable internalized skill: {name}"

    @staticmethod
    def _infer_skill_inputs(runtime_func: object | None) -> tuple[ToolIOField, ...]:
        if not callable(runtime_func):
            return (ToolIOField(name="user_request", type_name="string"),)
        try:
            signature = inspect.signature(runtime_func)
        except (TypeError, ValueError):
            return (ToolIOField(name="user_request", type_name="string"),)

        fields: list[ToolIOField] = []
        for param in signature.parameters.values():
            if param.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                continue
            annotation = "string"
            if param.annotation is not inspect._empty:
                annotation = getattr(param.annotation, "__name__", str(param.annotation))
            fields.append(
                ToolIOField(
                    name=param.name,
                    type_name=annotation,
                    required=param.default is inspect._empty,
                )
            )
        return tuple(fields or (ToolIOField(name="user_request", type_name="string"),))

    @staticmethod
    def _infer_skill_outputs(runtime_func: object | None) -> tuple[ToolIOField, ...]:
        if not callable(runtime_func):
            return (ToolIOField(name="result", type_name="string"),)
        try:
            signature = inspect.signature(runtime_func)
        except (TypeError, ValueError):
            return (ToolIOField(name="result", type_name="string"),)

        annotation = "string"
        if signature.return_annotation is not inspect._empty:
            annotation = getattr(signature.return_annotation, "__name__", str(signature.return_annotation))
        return (ToolIOField(name="result", type_name=annotation),)

    def create_discovery_engine(self) -> ToolDiscoveryEngine:
        return ToolDiscoveryEngine(self.build_tool_knowledge_base())

    def handle_tool_spec(
        self,
        *,
        tool_spec: ToolSpec,
        tool_context: ProjectToolContext,
        spec_source: str,
        loop_compactor: LoopContextCompactor | None = None,
        allow_teacher_repair: bool = True,
    ) -> tuple[str, ToolSpec | None]:
        readiness = self.tool_builder.assess_readiness(tool_spec)
        if readiness.ready:
            self.persist_tool_contract(
                tool_spec=tool_spec,
                tool_context=tool_context,
                source=spec_source,
            )
            outline = self.tool_builder.build_outline(
                ToolBuildRequest(
                    context=tool_context,
                    spec=tool_spec,
                )
            )
            return (
                "Observation: Tool contract accepted.\n"
                f"{outline}\n"
                "Next step: implement or compose this tool with python_repl, then continue.",
                tool_spec,
            )

        if not allow_teacher_repair:
            return (
                "Observation: Tool contract is still incomplete after teacher repair.\n"
                f"Missing items: {', '.join(readiness.missing_items) or '(none)'}\n"
                "Next step: repair the remaining fields before implementation.",
                None,
            )

        teacher_request = self.teacher_escalation.create_request(
            kind=HelpRequestKind.REPAIR_TOOL_CONTRACT,
            context=tool_context,
            current_spec=tool_spec,
            failures=[
                ToolFailureRecord(
                    stage="contract_validation",
                    reason="missing=" + ",".join(readiness.missing_items or ("unknown",)),
                )
            ],
        )
        teacher_reply = self.request_teacher_help(teacher_request)
        if loop_compactor is not None:
            loop_compactor.record_teacher_guidance(teacher_reply)
        repaired_spec = ToolLifecycleParser.parse_tool_spec(teacher_reply)
        if repaired_spec is not None:
            if loop_compactor is not None:
                loop_compactor.record_tool_spec(repaired_spec, source="teacher")
            repaired_follow_up, accepted_spec = self.handle_tool_spec(
                tool_spec=repaired_spec,
                tool_context=tool_context,
                spec_source="teacher",
                loop_compactor=loop_compactor,
                allow_teacher_repair=False,
            )
            return (
                "Observation: Teacher returned a repaired tool contract.\n"
                f"{repaired_follow_up}",
                accepted_spec,
            )
        return (
            "Observation: Tool contract is incomplete.\n"
            f"Missing items: {', '.join(readiness.missing_items) or '(none)'}\n"
            "Teacher guidance follows.\n"
            f"{teacher_reply}",
            None,
        )

    def persist_tool_contract(
        self,
        *,
        tool_spec: ToolSpec,
        tool_context: ProjectToolContext,
        source: str,
    ) -> None:
        self.tool_registry.upsert_spec(
            spec=tool_spec,
            project_id=tool_context.project_id,
            source=tool_context.task_summary,
            origin=source,
            tier=PromotionTier.EPISODE,
            note=f"accepted_from={source}",
        )

    def record_contract_outcome(
        self,
        *,
        tool_spec: ToolSpec,
        project_id: str,
        success: bool,
        notes: str,
        trace_id: str,
    ) -> None:
        execution = ToolExecutionRecord(
            tool_name=tool_spec.name,
            project_id=project_id,
            success=success,
            matched_contract=True,
            latency_ms=0,
            reused_existing_tool=self.skill_selector.has_skill(tool_spec.name),
            internalized_after_run=self.skill_selector.has_skill(tool_spec.name),
            notes=notes,
        )
        self.tool_registry.add_execution(execution)
        decision = self.tool_promotion.decide(self.tool_registry.executions_for(tool_spec.name))
        upgraded = self.tool_registry.apply_promotion(tool_spec.name, decision)
        self.maybe_internalize_promoted_tool(
            tool_name=tool_spec.name,
            decision=decision,
            trace_id=trace_id,
        )
        self.skill_event_logger.log(
            "tool_promotion_evaluated",
            trace_id,
            {
                "tool_name": tool_spec.name,
                "success": success,
                "reuse_score": decision.score.reuse_score,
                "internalize_score": decision.score.internalize_score,
                "tier": decision.tier.value,
                "should_promote": decision.should_promote,
                "registry_updated": upgraded is not None,
            },
        )

    def maybe_capture_contract_implementation(
        self,
        *,
        messages: list[dict[str, str]],
        response_text: str,
        active_contract: ToolSpec,
        trace_id: str,
    ) -> None:
        for candidate in self.collect_code_from_messages(messages):
            validation = self.skill_manager.validate(candidate)
            if not validation.is_valid or not validation.function_name:
                continue
            if validation.function_name != active_contract.name:
                continue
            attached = self.tool_registry.attach_implementation(
                active_contract.name,
                validation.normalized_code.strip(),
            )
            if attached is not None:
                self.skill_event_logger.log(
                    "tool_implementation_attached",
                    trace_id,
                    {
                        "tool_name": active_contract.name,
                        "source": "messages",
                    },
                )
                return

        for candidate in self.collect_code_candidates(response_text):
            validation = self.skill_manager.validate(candidate)
            if not validation.is_valid or not validation.function_name:
                continue
            if validation.function_name != active_contract.name:
                continue
            attached = self.tool_registry.attach_implementation(
                active_contract.name,
                validation.normalized_code.strip(),
            )
            if attached is not None:
                self.skill_event_logger.log(
                    "tool_implementation_attached",
                    trace_id,
                    {
                        "tool_name": active_contract.name,
                        "source": "response",
                    },
                )
                return

    def maybe_internalize_promoted_tool(
        self,
        *,
        tool_name: str,
        decision: PromotionDecision,
        trace_id: str,
    ) -> None:
        if decision.tier != PromotionTier.GLOBAL or not decision.should_promote:
            return
        if self.skill_manager.has_skill(tool_name):
            return
        record = self.tool_registry.get_record(tool_name)
        if record is None or not record.implementation_code.strip():
            return
        workbench_result = self.skill_workbench.evaluate(
            function_code=record.implementation_code,
            spec=record.spec,
        )
        if not workbench_result.is_valid:
            self.skill_event_logger.log(
                "tool_internalize_failed",
                trace_id,
                {
                    "tool_name": tool_name,
                    "reason": "; ".join(workbench_result.errors)[:200],
                },
            )
            return
        try:
            skill_name = self.skill_manager.append_skill(
                source=record.source or record.spec.purpose,
                function_code=workbench_result.normalized_code,
            )
        except ValueError as exc:
            self.skill_event_logger.log(
                "tool_internalize_failed",
                trace_id,
                {"tool_name": tool_name, "reason": str(exc)[:200]},
            )
            return
        self.skill_event_logger.log(
            "tool_internalized_from_registry",
            trace_id,
            {"tool_name": tool_name, "skill_name": skill_name},
        )

    def request_teacher_help(self, request: object) -> str:
        prompt = (
            "You are a larger-model teacher that helps a smaller agent repair or propose tools.\n"
            "Return a fenced ```tool_spec``` JSON block whenever you repair or propose a contract.\n"
            "After the block, add at most three concise notes.\n\n"
            f"{self.serialize_teacher_request(request)}"
        )
        result = self.llm.chat_with_meta(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            route_hint="large",
        )
        return result.content.strip()

    @staticmethod
    def serialize_teacher_request(request: object) -> str:
        if hasattr(request, "__dict__"):
            return json.dumps(request.__dict__, ensure_ascii=False, default=str, indent=2)
        return str(request)

    @staticmethod
    def collect_code_candidates(text: str) -> list[str]:
        if not text.strip():
            return []
        out: list[str] = []

        for block in re.findall(r"```(?:python)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
            candidate = block.strip()
            if "def " in candidate:
                out.append(candidate)

        if out:
            return out

        marker = "def "
        idx = text.find(marker)
        if idx >= 0:
            out.append(text[idx:].strip())
        return out

    @staticmethod
    def collect_code_from_messages(messages: list[dict[str, str]]) -> list[str]:
        out: list[str] = []
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            action = ReActParser.parse_action(content)
            if action and action.tool_name == "python_repl":
                code = action.tool_input.strip()
                if code:
                    out.append(code)
        return out
