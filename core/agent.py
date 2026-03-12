"""Cognitive agent orchestration.

This module focuses on workflow orchestration and delegates domain work to
specialized components (LLM, memory, tools, emotion, evolution).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

import yaml

from config.settings import AppConfig, load_config
from core.context_compactor import LoopContextCompactor
from core.evolution import SkillEvolver
from core.llm_interface import LLMInterface
from core.react_parser import ReActParser
from core.scorer import RuleBasedScorer
from memory.vector_store import MemorySystem
from memory.working_memory import WorkingMemory
from modules.emotion import EmotionEngine
from modules.tools import ToolBox
from skills.event_logger import SkillEventLogger
from skills.manager import SkillManager
from skills.selector import SkillCandidate, SkillSelector
from skills.tool_builder import ToolBuilderPlanner
from skills.tool_contracts import (
    HelpRequestKind,
    PromotionTier,
    ProjectToolContext,
    ToolBuildRequest,
    ToolExecutionRecord,
    ToolFailureRecord,
    ToolIOField,
    ToolKnowledgeBase,
    ToolMatchResult,
    ToolSpec,
)
from skills.tool_discovery import ToolDiscoveryEngine
from skills.tool_escalation import TeacherEscalationPlanner
from skills.tool_parser import ToolLifecycleParser
from skills.tool_promotion import ToolPromotionPolicy
from skills.tool_registry import ToolRegistry


class CognitiveAgent:
    """Top-level coordinator for CoALA runtime."""

    def __init__(
        self,
        config: AppConfig | None = None,
        llm: LLMInterface | None = None,
        working_memory: WorkingMemory | None = None,
        long_term_memory: MemorySystem | None = None,
        tools: ToolBox | None = None,
        emotion_engine: EmotionEngine | None = None,
        evolver: SkillEvolver | None = None,
        skill_manager: SkillManager | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.config = config or load_config()
        self.prompts = self._load_prompts()

        self.llm = llm or LLMInterface(self.config)
        self.working_memory = working_memory or WorkingMemory()
        self.long_term_memory = long_term_memory or MemorySystem(self.config.memory)
        self.tools = tools or ToolBox()
        self.emotion_engine = emotion_engine or EmotionEngine(self.llm)
        self.skill_manager = skill_manager or SkillManager()
        self.skill_selector = SkillSelector(self.skill_manager)
        self.skill_event_logger = SkillEventLogger(
            enabled=self.config.skills.enable_event_log,
            event_log_dir=self.config.skills.event_log_dir,
        )
        self.evolver = evolver or SkillEvolver(self.llm, self.skill_manager)
        self.scorer = RuleBasedScorer()
        registry_path = Path(__file__).parent.parent / "data" / "tool_registry.json"
        self.tool_registry = tool_registry or ToolRegistry(index_file=registry_path)
        self.tool_promotion = ToolPromotionPolicy()
        self.tool_knowledge_base = self._build_tool_knowledge_base()
        self.tool_discovery = ToolDiscoveryEngine(self.tool_knowledge_base)
        self.tool_builder = ToolBuilderPlanner()
        self.teacher_escalation = TeacherEscalationPlanner()

        empty_context = self._build_project_tool_context("")
        self._refresh_system_prompt(
            mood=self.emotion_engine.current_mood,
            memories=[],
            skill_candidates=[],
            tool_context=empty_context,
            tool_matches=[],
            loop_brief="",
        )

    def run(self, user_input: str) -> str:
        trace_id = self._new_trace_id()
        self._reload_tool_runtime_state()
        memory_result = self.long_term_memory.search(
            query=user_input,
            n_results=self.config.agent.memory_top_k,
            trace_id=trace_id,
            query_type="task_context",
        )
        related_memories = memory_result.get("documents", [])
        skill_candidates = self.skill_selector.recommend(
            query=user_input,
            top_k=self.config.skills.candidate_top_k,
        )
        self.skill_event_logger.log(
            "skill_candidates",
            trace_id,
            {
                "query": user_input,
                "candidates": [
                    {"name": item.name, "score": item.score}
                    for item in skill_candidates
                ],
            },
        )

        tool_context = self._build_project_tool_context(user_input)
        tool_matches = self.tool_discovery.recommend(tool_context, top_k=3)
        loop_compactor = LoopContextCompactor(
            keep_recent_messages=self.config.agent.keep_recent_messages,
            compress_trigger=self.config.agent.compact_history_trigger,
        )
        loop_compactor.start_run(goal=user_input, tool_matches=tool_matches)

        mood = self.emotion_engine.update_mood(user_input, related_memories)
        self._refresh_system_prompt(
            mood=mood,
            memories=related_memories,
            skill_candidates=skill_candidates,
            tool_context=tool_context,
            tool_matches=tool_matches,
            loop_brief=loop_compactor.build_brief(),
        )
        self.working_memory.add_message("user", user_input)

        messages = self.working_memory.get_context()
        tool_steps = 0
        active_contract: ToolSpec | None = None

        for _ in range(self.config.agent.max_steps):
            self._refresh_system_prompt(
                mood=mood,
                memories=related_memories,
                skill_candidates=skill_candidates,
                tool_context=tool_context,
                tool_matches=tool_matches,
                loop_brief=loop_compactor.build_brief(),
            )
            if messages and messages[0].get("role") == "system":
                messages[0] = dict(self.working_memory.get_context()[0])
            messages_for_model = loop_compactor.compact_messages(messages)
            llm_result = self.llm.chat_with_meta(
                messages=messages_for_model,
                temperature=self.config.agent.default_temperature,
                route_hint="auto",
            )
            response = llm_result.content

            action = ReActParser.parse_action(response)
            if action:
                tool_steps += 1
                action_started = time.perf_counter()
                loop_compactor.record_action(action.tool_name, action.tool_input)
                is_internalized_skill = self.skill_selector.has_skill(action.tool_name)
                if is_internalized_skill:
                    self.skill_event_logger.log(
                        "skill_called",
                        trace_id,
                        {
                            "tool_name": action.tool_name,
                            "tool_input_preview": action.tool_input[:160],
                        },
                    )
                observation = self.tools.execute(action.tool_name, action.tool_input)
                action_latency_ms = int((time.perf_counter() - action_started) * 1000)
                if is_internalized_skill:
                    event_type = "skill_success"
                    lowered_observation = observation.lower()
                    if "error" in lowered_observation or "not found" in lowered_observation:
                        event_type = "skill_fail"
                    self.skill_event_logger.log(
                        event_type,
                        trace_id,
                        {
                            "tool_name": action.tool_name,
                            "observation_preview": observation[:200],
                        },
                    )
                    self.tool_registry.add_execution(
                        ToolExecutionRecord(
                            tool_name=action.tool_name,
                            project_id=tool_context.project_id,
                            success=event_type == "skill_success",
                            matched_contract=True,
                            latency_ms=action_latency_ms,
                            reused_existing_tool=True,
                            internalized_after_run=True,
                            notes="internalized skill execution",
                        )
                    )
                loop_compactor.record_observation(observation)
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue

            tool_spec = ToolLifecycleParser.parse_tool_spec(response)
            if tool_spec is not None:
                loop_compactor.record_tool_spec(tool_spec, source="small_model")
                messages.append({"role": "assistant", "content": response})
                follow_up, accepted_spec = self._handle_tool_spec(
                    tool_spec=tool_spec,
                    tool_context=tool_context,
                    spec_source="small_model",
                    loop_compactor=loop_compactor,
                )
                if accepted_spec is not None:
                    active_contract = accepted_spec
                    self._reload_tool_runtime_state()
                loop_compactor.record_observation(follow_up)
                messages.append({"role": "user", "content": follow_up})
                continue

            final_answer = ReActParser.parse_final_answer(response)
            if final_answer:
                loop_compactor.record_completion(final_answer)
                score = self.scorer.score(
                    response_text=response,
                    tool_steps=tool_steps,
                    memory_hits=len(related_memories),
                    reached_final_answer=True,
                )
                self._try_evolve(
                    messages=messages,
                    user_input=user_input,
                    response_text=response,
                    trace_id=trace_id,
                )
                if active_contract is not None:
                    self._record_contract_outcome(
                        tool_spec=active_contract,
                        project_id=tool_context.project_id,
                        success=True,
                        notes="final_answer_reached",
                        trace_id=trace_id,
                    )
                self.long_term_memory.add(
                    text=f"User: {user_input} | Agent: {final_answer}",
                    metadata={
                        "type": "conversation",
                        "route": llm_result.route,
                        "model": llm_result.model_name,
                    },
                    trace_id=trace_id,
                    write_reason="final_answer",
                    source="self_generated",
                    score_snapshot=score.as_dict(),
                )
                self.working_memory.add_message("assistant", final_answer)
                return final_answer

            score = self.scorer.score(
                response_text=response,
                tool_steps=tool_steps,
                memory_hits=len(related_memories),
                reached_final_answer=False,
            )
            self.long_term_memory.add(
                text=f"User: {user_input} | Agent: {response}",
                metadata={
                    "type": "fallback_response",
                    "route": llm_result.route,
                    "model": llm_result.model_name,
                },
                trace_id=trace_id,
                write_reason="fallback_response",
                source="self_generated",
                score_snapshot=score.as_dict(),
            )
            self._try_evolve(
                messages=messages,
                user_input=user_input,
                response_text=response,
                trace_id=trace_id,
            )
            if active_contract is not None:
                self._record_contract_outcome(
                    tool_spec=active_contract,
                    project_id=tool_context.project_id,
                    success=False,
                    notes="fallback_response_without_final_answer",
                    trace_id=trace_id,
                )
            self.working_memory.add_message("assistant", response)
            return response

        timeout_response = "任务已停止：达到最大推理步数。"
        score = self.scorer.score(
            response_text=timeout_response,
            tool_steps=tool_steps,
            memory_hits=len(related_memories),
            reached_final_answer=False,
        )
        self.long_term_memory.add(
            text=f"User: {user_input} | Agent: {timeout_response}",
            metadata={"type": "timeout_response", "reason": "max_steps_reached"},
            trace_id=trace_id,
            write_reason="max_steps_timeout",
            source="self_generated",
            score_snapshot=score.as_dict(),
        )
        if active_contract is not None:
            self._record_contract_outcome(
                tool_spec=active_contract,
                project_id=tool_context.project_id,
                success=False,
                notes="max_steps_timeout",
                trace_id=trace_id,
            )
        self.working_memory.add_message("assistant", timeout_response)
        return timeout_response

    def _handle_tool_spec(
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
            self._persist_tool_contract(
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
        teacher_reply = self._request_teacher_help(teacher_request)
        if loop_compactor is not None:
            loop_compactor.record_teacher_guidance(teacher_reply)
        repaired_spec = ToolLifecycleParser.parse_tool_spec(teacher_reply)
        if repaired_spec is not None:
            if loop_compactor is not None:
                loop_compactor.record_tool_spec(repaired_spec, source="teacher")
            repaired_follow_up, accepted_spec = self._handle_tool_spec(
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

    def _request_teacher_help(self, request: object) -> str:
        prompt = (
            "You are a larger-model teacher that helps a smaller agent repair or propose tools.\n"
            "Return a fenced ```tool_spec``` JSON block whenever you repair or propose a contract.\n"
            "After the block, add at most three concise notes.\n\n"
            f"{self._serialize_teacher_request(request)}"
        )
        result = self.llm.chat_with_meta(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            route_hint="large",
        )
        return result.content.strip()

    @staticmethod
    def _serialize_teacher_request(request: object) -> str:
        if hasattr(request, "__dict__"):
            return json.dumps(request.__dict__, ensure_ascii=False, default=str, indent=2)
        return str(request)

    def _refresh_system_prompt(
        self,
        mood: str,
        memories: list[str],
        skill_candidates: list[SkillCandidate],
        tool_context: ProjectToolContext,
        tool_matches: list[ToolMatchResult],
        loop_brief: str,
    ) -> None:
        template = self.prompts.get("system_persona", self._default_system_template())
        memories_text = "\n".join(f"- {item}" for item in memories) if memories else "[暂无相关记忆]"
        base_prompt = template.format(
            mood=mood,
            tool_desc=self.tools.get_tool_desc(),
            memories=memories_text,
        )
        prompt = self._append_language_instruction(base_prompt)
        prompt = self._append_skill_candidates_instruction(
            prompt=prompt,
            candidates=skill_candidates,
        )
        prompt = self._append_tool_lifecycle_instruction(
            prompt=prompt,
            tool_context=tool_context,
            tool_matches=tool_matches,
        )
        prompt = self._append_execution_brief_instruction(
            prompt=prompt,
            loop_brief=loop_brief,
        )
        self.working_memory.replace_system_prompt(prompt)

    @staticmethod
    def _load_prompts() -> dict:
        prompt_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
        if not prompt_path.exists():
            return {"system_persona": CognitiveAgent._default_system_template()}

        with prompt_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "system_persona" not in data:
            data["system_persona"] = CognitiveAgent._default_system_template()
        return data

    @staticmethod
    def _default_system_template() -> str:
        return (
            "你是 Neko，一个会调用工具的智能体。\n"
            "当前情绪：{mood}\n\n"
            "[可用工具]\n{tool_desc}\n\n"
            "[相关记忆]\n{memories}\n\n"
            "当需要使用工具时，必须使用 ReAct 格式：\n"
            "Thought: ...\n"
            "Action: <tool_name>\n"
            "Action Input: <tool_input>\n"
            "Observation: <tool_output>\n"
            "Final Answer: <answer>\n"
        )

    @staticmethod
    def _new_trace_id() -> str:
        return f"tr_{uuid.uuid4().hex}"

    def _append_language_instruction(self, prompt: str) -> str:
        language = self.config.agent.response_language.strip().lower()
        if language in {"zh", "zh-cn", "zh-hans", "chinese"}:
            return (
                f"{prompt}\n\n"
                "[语言要求]\n"
                "1. 与用户交互时，默认使用简体中文。\n"
                "2. 除非用户明确要求其他语言，否则不要切换为英文回答。\n"
                "3. 代码、命令、路径、API 字段名保持原文。\n"
            )
        return prompt

    @staticmethod
    def _append_skill_candidates_instruction(
        *,
        prompt: str,
        candidates: list[SkillCandidate],
    ) -> str:
        if not candidates:
            return prompt
        lines = [
            prompt,
            "",
            "[候选内部技能]",
            "以下技能与当前任务可能相关，若可满足需求请优先调用，避免重复编写 python_repl 代码：",
        ]
        for idx, item in enumerate(candidates, 1):
            lines.append(
                f"{idx}. {item.name} (score={item.score:.2f}) - source: {item.source_excerpt}"
            )
        return "\n".join(lines)

    def _append_tool_lifecycle_instruction(
        self,
        *,
        prompt: str,
        tool_context: ProjectToolContext,
        tool_matches: list[ToolMatchResult],
    ) -> str:
        lines = [
            prompt,
            "",
            "[项目工具上下文]",
            f"任务: {tool_context.task_summary or '(empty)'}",
            "策略: 先复用合适工具；若没有合适工具，先定义 Tool Spec；再决定是否实现；构建受阻时再向大模型发起结构化求助。",
        ]

        if tool_context.existing_tools:
            lines.append(f"已知工具: {', '.join(tool_context.existing_tools)}")
        else:
            lines.append("已知工具: (none)")

        if tool_matches:
            lines.append("")
            lines.append("[工具匹配结果]")
            for idx, item in enumerate(tool_matches, 1):
                lines.append(
                    f"{idx}. {item.spec.name} score={item.breakdown.total_score:.2f} "
                    f"purpose={item.spec.purpose}"
                )
        else:
            teacher_request = self.teacher_escalation.create_request(
                kind=HelpRequestKind.PROPOSE_NEW_TOOL,
                context=tool_context,
                current_spec=None,
                failures=[
                    ToolFailureRecord(
                        stage="discovery",
                        reason="no high-confidence tool match in current project context",
                    )
                ],
            )
            lines.extend(
                [
                    "",
                    "[工具策略]",
                    "当前没有高置信可复用工具。",
                    "请先输出一个 ```tool_spec ...``` JSON 代码块。",
                    "Tool Spec 至少包含: name, purpose, inputs, outputs, side_effects, failure_modes, examples。",
                    "如果契约不完整，系统会自动请求大模型给出修复建议。",
                    f"建议求助类型: {teacher_request.kind.value}",
                    f"建议求助输出: {teacher_request.requested_output}",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _append_execution_brief_instruction(*, prompt: str, loop_brief: str) -> str:
        if not loop_brief.strip():
            return prompt
        return f"{prompt}\n\n{loop_brief}"

    def _build_project_tool_context(self, user_input: str) -> ProjectToolContext:
        return ProjectToolContext(
            project_id="active-session",
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

    def _build_tool_knowledge_base(self) -> ToolKnowledgeBase:
        specs: list[ToolSpec] = []
        seen: set[str] = set()
        for record in self.skill_manager.catalog.list_records():
            if not record.enabled:
                continue
            specs.append(
                ToolSpec(
                    name=record.name,
                    purpose=record.source.strip() or f"Reusable internalized skill: {record.name}",
                    inputs=(ToolIOField(name="user_request", type_name="string"),),
                    outputs=(ToolIOField(name="result", type_name="string"),),
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

    def _reload_tool_runtime_state(self) -> None:
        self.tool_knowledge_base = self._build_tool_knowledge_base()
        self.tool_discovery = ToolDiscoveryEngine(self.tool_knowledge_base)

    def _persist_tool_contract(
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

    def _record_contract_outcome(
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

    def _try_evolve(
        self,
        messages: list[dict[str, str]],
        user_input: str,
        response_text: str,
        trace_id: str,
    ) -> None:
        candidates: list[str] = []

        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            action = ReActParser.parse_action(content)
            if not action or action.tool_name != "python_repl":
                continue

            code = action.tool_input
            if len(code) < 16:
                continue
            if any(token in code for token in ["def ", "for ", "while ", "import "]):
                candidates.append(code)
                break

        candidates.extend(self._collect_code_candidates(response_text))

        seen: set[str] = set()
        for candidate_code in candidates:
            normalized = candidate_code.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            validation = self.skill_manager.validate(normalized)
            if validation.is_valid and validation.function_name:
                if self.skill_manager.has_skill(validation.function_name):
                    self.skill_event_logger.log(
                        "skill_internalize_skipped_existing",
                        trace_id,
                        {"skill_name": validation.function_name},
                    )
                    return
                try:
                    skill_name = self.skill_manager.append_skill(
                        source=user_input,
                        function_code=normalized,
                    )
                    self.skill_event_logger.log(
                        "skill_internalized",
                        trace_id,
                        {"skill_name": skill_name, "source": "direct_extract"},
                    )
                    return
                except ValueError as exc:
                    self.skill_event_logger.log(
                        "skill_internalize_failed",
                        trace_id,
                        {"reason": str(exc)[:200]},
                    )
                    continue

            if any(token in normalized for token in ["def ", "for ", "while ", "import "]):
                ok = self.evolver.evolve(user_intent=user_input, successful_code=normalized)
                event_type = (
                    "skill_internalized_via_evolver"
                    if ok
                    else "skill_internalize_failed"
                )
                self.skill_event_logger.log(
                    event_type,
                    trace_id,
                    {"source": "evolver"},
                )
                if ok:
                    return

    @staticmethod
    def _collect_code_candidates(text: str) -> list[str]:
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
