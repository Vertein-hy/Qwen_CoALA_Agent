"""Cognitive agent orchestration."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from config.settings import AppConfig, load_config
from core.agent_prompt_builder import AgentPromptBuilder
from core.agent_trace import AgentTraceRecorder
from core.context_compactor import LoopContextCompactor
from core.evolution import SkillEvolver
from core.llm_interface import LLMInterface
from core.loop_guard import LoopGuard
from core.react_parser import ReActParser
from core.scorer import RuleBasedScorer
from core.skill_routing import DirectSkillCall, SkillRouter
from core.tool_lifecycle_runtime import ToolLifecycleRuntime
from memory.vector_store import MemorySystem
from memory.working_memory import WorkingMemory
from modules.emotion import EmotionEngine
from modules.tools import ToolBox
from rl.contracts import DecisionAction, PolicySuggestion
from rl.runtime_router import RLRuntimeRouter
from skills.event_logger import SkillEventLogger
from skills.manager import SkillManager
from skills.selector import SkillCandidate, SkillSelector
from skills.tool_builder import ToolBuilderPlanner
from skills.tool_contracts import ProjectToolContext, ToolExecutionRecord, ToolMatchResult, ToolSpec
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
        self.tool_builder = ToolBuilderPlanner()
        self.teacher_escalation = TeacherEscalationPlanner()
        self.tool_runtime = ToolLifecycleRuntime(
            config=self.config,
            llm=self.llm,
            skill_manager=self.skill_manager,
            skill_selector=self.skill_selector,
            skill_event_logger=self.skill_event_logger,
            tool_registry=self.tool_registry,
            tool_promotion=self.tool_promotion,
            tool_builder=self.tool_builder,
            teacher_escalation=self.teacher_escalation,
        )
        self.prompt_builder = AgentPromptBuilder(
            config=self.config,
            teacher_escalation=self.teacher_escalation,
        )
        self.tool_knowledge_base = self.tool_runtime.build_tool_knowledge_base()
        self.tool_discovery = ToolDiscoveryEngine(self.tool_knowledge_base)
        self.rl_runtime_router = RLRuntimeRouter()
        self._active_trace: AgentTraceRecorder | None = None
        self._active_rl_gate_note = ""

        empty_context = self.tool_runtime.build_project_tool_context("")
        self._refresh_system_prompt(
            mood=self.emotion_engine.current_mood,
            memories=[],
            skill_candidates=[],
            tool_context=empty_context,
            tool_matches=[],
            loop_brief="",
        )

    def run(self, user_input: str) -> str:
        return str(self.run_with_trace(user_input)["reply"])

    def run_with_trace(self, user_input: str) -> dict[str, object]:
        trace_id = self._new_trace_id()
        self._active_trace = AgentTraceRecorder(trace_id=trace_id, user_input=user_input)
        self._reload_tool_runtime_state()
        related_memories = self._load_related_memories(user_input, trace_id)
        skill_candidates = self._load_skill_candidates(user_input, trace_id)

        tool_context = self.tool_runtime.build_project_tool_context(user_input)
        tool_matches = self.tool_discovery.recommend(tool_context, top_k=3)
        routing_tool_matches = self._expand_direct_route_candidates(
            user_input=user_input,
            tool_context=tool_context,
            initial_matches=tool_matches,
        )
        loop_compactor = LoopContextCompactor(
            keep_recent_messages=self.config.agent.keep_recent_messages,
            compress_trigger=self.config.agent.compact_history_trigger,
        )
        loop_guard = LoopGuard(
            repeated_response_limit=self.config.agent.repeated_response_limit,
            repeated_tool_cycle_limit=self.config.agent.repeated_tool_cycle_limit,
        )
        loop_compactor.start_run(goal=user_input, tool_matches=tool_matches)
        self._record_trace_candidates(skill_candidates=skill_candidates, tool_matches=tool_matches)
        self._active_rl_gate_note = ""
        rl_suggestion = self._record_rl_policy_suggestion(
            user_input=user_input,
            skill_candidates=skill_candidates,
            tool_matches=tool_matches,
        )
        gated_direct_call = self._apply_rl_policy_gate(
            suggestion=rl_suggestion,
            user_input=user_input,
            tool_matches=routing_tool_matches,
        )

        mood = self.emotion_engine.update_mood(user_input, related_memories)
        self._refresh_system_prompt(
            mood=mood,
            memories=related_memories,
            skill_candidates=skill_candidates,
            tool_context=tool_context,
            tool_matches=tool_matches,
            loop_brief=self._compose_loop_brief(loop_compactor.build_brief()),
        )
        self.working_memory.add_message("user", user_input)

        messages = self.working_memory.get_context()
        tool_steps = 0
        active_contract: ToolSpec | None = None

        direct_skill_call = gated_direct_call or SkillRouter.infer_direct_skill_call(
            user_input=user_input,
            tool_matches=routing_tool_matches,
            executable_tool_names=self._executable_tool_names(),
        )
        if direct_skill_call is not None:
            self._record_trace_step(
                kind="direct_route",
                title="Direct Tool Route",
                content=f"{direct_skill_call.tool_name}({direct_skill_call.tool_input})",
                metadata={"reason": direct_skill_call.reason, "matched_via": direct_skill_call.matched_via},
            )
            return self._finalize_direct_skill_call(
                user_input=user_input,
                direct_skill_call=direct_skill_call,
                trace_id=trace_id,
                related_memories=related_memories,
                tool_context=tool_context,
                loop_compactor=loop_compactor,
                messages=messages,
            )

        for _ in range(self.config.agent.max_steps):
            messages_for_model = self._prepare_messages_for_model(
                messages=messages,
                mood=mood,
                related_memories=related_memories,
                skill_candidates=skill_candidates,
                tool_context=tool_context,
                tool_matches=tool_matches,
                loop_compactor=loop_compactor,
            )
            llm_result = self.llm.chat_with_meta(
                messages=messages_for_model,
                temperature=self.config.agent.default_temperature,
                route_hint="auto",
            )
            response = llm_result.content
            self._record_trace_step(
                kind="llm_response",
                title="LLM Response",
                content=response,
                metadata={"route": llm_result.route, "model_name": llm_result.model_name},
            )
            if loop_guard.record_response(response):
                return self._finalize_fallback(
                    user_input=user_input,
                    response="任务已停止：模型重复输出相同内容且没有新进展。请改用其他工具、修正 Tool Spec，或直接给出最终答案。",
                    trace_id=trace_id,
                    related_memories=related_memories,
                    tool_steps=tool_steps,
                    tool_context=tool_context,
                    active_contract=active_contract,
                    messages=messages,
                    route=llm_result.route,
                    model_name=llm_result.model_name,
                )

            action = ReActParser.parse_action(response)
            if action:
                tool_steps += 1
                observation = self._handle_action_step(
                    action_name=action.tool_name,
                    action_input=action.tool_input,
                    trace_id=trace_id,
                    tool_context=tool_context,
                    loop_compactor=loop_compactor,
                    messages=messages,
                )
                if loop_guard.record_tool_cycle(
                    tool_name=action.tool_name,
                    tool_input=action.tool_input,
                    observation=observation,
                ):
                    return self._finalize_fallback(
                        user_input=user_input,
                        response="任务已停止：重复执行同一工具且没有新进展。请修正工具输入、改用其他工具，或直接输出最终答案。",
                        trace_id=trace_id,
                        related_memories=related_memories,
                        tool_steps=tool_steps,
                        tool_context=tool_context,
                        active_contract=active_contract,
                        messages=messages,
                        route=llm_result.route,
                        model_name=llm_result.model_name,
                    )
                if SkillRouter.should_finalize_from_observation(
                    user_input=user_input,
                    action_name=action.tool_name,
                    observation=observation,
                ):
                    return self._finalize_success(
                        user_input=user_input,
                        response=f"Final Answer: {observation}",
                        final_answer=observation,
                        trace_id=trace_id,
                        related_memories=related_memories,
                        tool_steps=tool_steps,
                        tool_context=tool_context,
                        active_contract=active_contract,
                        loop_compactor=loop_compactor,
                        messages=messages,
                        route=llm_result.route,
                        model_name=llm_result.model_name,
                    )
                continue

            tool_spec = ToolLifecycleParser.parse_tool_spec(response)
            if tool_spec is not None:
                self._record_trace_step(
                    kind="tool_spec",
                    title="Tool Spec",
                    content=response,
                    metadata={"source": "small_model", "tool_name": tool_spec.name},
                )
                loop_compactor.record_tool_spec(tool_spec, source="small_model")
                messages.append({"role": "assistant", "content": response})
                follow_up, accepted_spec = self.tool_runtime.handle_tool_spec(
                    tool_spec=tool_spec,
                    tool_context=tool_context,
                    spec_source="small_model",
                    loop_compactor=loop_compactor,
                )
                if accepted_spec is not None:
                    active_contract = accepted_spec
                    self._reload_tool_runtime_state()
                self._record_trace_step(
                    kind="tool_spec_follow_up",
                    title="Tool Spec Follow-up",
                    content=follow_up,
                    metadata={"accepted": accepted_spec is not None},
                )
                loop_compactor.record_observation(follow_up)
                messages.append({"role": "user", "content": follow_up})
                continue

            final_answer = ReActParser.parse_final_answer(response)
            if final_answer:
                return self._finalize_success(
                    user_input=user_input,
                    response=response,
                    final_answer=final_answer,
                    trace_id=trace_id,
                    related_memories=related_memories,
                    tool_steps=tool_steps,
                    tool_context=tool_context,
                    active_contract=active_contract,
                    loop_compactor=loop_compactor,
                    messages=messages,
                    route=llm_result.route,
                    model_name=llm_result.model_name,
                )

            return self._finalize_fallback(
                user_input=user_input,
                response=response,
                trace_id=trace_id,
                related_memories=related_memories,
                tool_steps=tool_steps,
                tool_context=tool_context,
                active_contract=active_contract,
                messages=messages,
                route=llm_result.route,
                model_name=llm_result.model_name,
            )

        return self._finalize_timeout(
            user_input=user_input,
            trace_id=trace_id,
            related_memories=related_memories,
            tool_steps=tool_steps,
            tool_context=tool_context,
            active_contract=active_contract,
            messages=messages,
        )

    def _load_related_memories(self, user_input: str, trace_id: str) -> list[str]:
        memory_result = self.long_term_memory.search(
            query=user_input,
            n_results=self.config.agent.memory_top_k,
            trace_id=trace_id,
            query_type="task_context",
        )
        return memory_result.get("documents", [])

    def _load_skill_candidates(self, user_input: str, trace_id: str) -> list[SkillCandidate]:
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
        return skill_candidates

    def _prepare_messages_for_model(
        self,
        *,
        messages: list[dict[str, str]],
        mood: str,
        related_memories: list[str],
        skill_candidates: list[SkillCandidate],
        tool_context: ProjectToolContext,
        tool_matches: list[ToolMatchResult],
        loop_compactor: LoopContextCompactor,
    ) -> list[dict[str, str]]:
        self._refresh_system_prompt(
            mood=mood,
            memories=related_memories,
            skill_candidates=skill_candidates,
            tool_context=tool_context,
            tool_matches=tool_matches,
            loop_brief=self._compose_loop_brief(loop_compactor.build_brief()),
        )
        if messages and messages[0].get("role") == "system":
            messages[0] = dict(self.working_memory.get_context()[0])
        return loop_compactor.compact_messages(messages)

    def _handle_action_step(
        self,
        *,
        action_name: str,
        action_input: str,
        trace_id: str,
        tool_context: ProjectToolContext,
        loop_compactor: LoopContextCompactor,
        messages: list[dict[str, str]],
    ) -> dict[str, object]:
        action_started = time.perf_counter()
        loop_compactor.record_action(action_name, action_input)
        self._record_trace_step(
            kind="action",
            title="Action",
            content=f"{action_name}({action_input})",
        )
        is_internalized_skill = self.skill_selector.has_skill(action_name)
        if is_internalized_skill:
            self.skill_event_logger.log(
                "skill_called",
                trace_id,
                {
                    "tool_name": action_name,
                    "tool_input_preview": action_input[:160],
                },
            )

        observation = self.tools.execute(action_name, action_input)
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
                    "tool_name": action_name,
                    "observation_preview": observation[:200],
                },
            )
            self.tool_registry.add_execution(
                ToolExecutionRecord(
                    tool_name=action_name,
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
        self._record_trace_step(
            kind="observation",
            title="Observation",
            content=observation,
            metadata={"tool_name": action_name, "latency_ms": action_latency_ms},
        )
        messages.append(
            {
                "role": "assistant",
                "content": (
                    f"Thought: tool execution\nAction: {action_name}\nAction Input: {action_input}"
                ),
            }
        )
        messages.append({"role": "user", "content": f"Observation: {observation}"})
        return observation

    def _finalize_success(
        self,
        *,
        user_input: str,
        response: str,
        final_answer: str,
        trace_id: str,
        related_memories: list[str],
        tool_steps: int,
        tool_context: ProjectToolContext,
        active_contract: ToolSpec | None,
        loop_compactor: LoopContextCompactor,
        messages: list[dict[str, str]],
        route: str,
        model_name: str,
    ) -> dict[str, object]:
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
            protected_skill_names=((active_contract.name,) if active_contract is not None else ()),
        )
        if active_contract is not None:
            self.tool_runtime.maybe_capture_contract_implementation(
                messages=messages,
                response_text=response,
                active_contract=active_contract,
                trace_id=trace_id,
            )
            self.tool_runtime.record_contract_outcome(
                tool_spec=active_contract,
                project_id=tool_context.project_id,
                success=True,
                notes="final_answer_reached",
                trace_id=trace_id,
            )
            self._reload_tool_runtime_state()

        self.long_term_memory.add(
            text=f"User: {user_input} | Agent: {final_answer}",
            metadata={"type": "conversation", "route": route, "model": model_name},
            trace_id=trace_id,
            write_reason="final_answer",
            source="self_generated",
            score_snapshot=score.as_dict(),
        )
        self.working_memory.add_message("assistant", final_answer)
        return self._finalize_trace(
            status="success",
            reply=final_answer,
            route=route,
            model_name=model_name,
        )

    def _finalize_fallback(
        self,
        *,
        user_input: str,
        response: str,
        trace_id: str,
        related_memories: list[str],
        tool_steps: int,
        tool_context: ProjectToolContext,
        active_contract: ToolSpec | None,
        messages: list[dict[str, str]],
        route: str,
        model_name: str,
    ) -> dict[str, object]:
        score = self.scorer.score(
            response_text=response,
            tool_steps=tool_steps,
            memory_hits=len(related_memories),
            reached_final_answer=False,
        )
        self.long_term_memory.add(
            text=f"User: {user_input} | Agent: {response}",
            metadata={"type": "fallback_response", "route": route, "model": model_name},
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
            protected_skill_names=((active_contract.name,) if active_contract is not None else ()),
        )
        if active_contract is not None:
            self.tool_runtime.maybe_capture_contract_implementation(
                messages=messages,
                response_text=response,
                active_contract=active_contract,
                trace_id=trace_id,
            )
            self.tool_runtime.record_contract_outcome(
                tool_spec=active_contract,
                project_id=tool_context.project_id,
                success=False,
                notes="fallback_response_without_final_answer",
                trace_id=trace_id,
            )
            self._reload_tool_runtime_state()

        self.working_memory.add_message("assistant", response)
        return self._finalize_trace(
            status="fallback",
            reply=response,
            route=route,
            model_name=model_name,
        )

    def _finalize_timeout(
        self,
        *,
        user_input: str,
        trace_id: str,
        related_memories: list[str],
        tool_steps: int,
        tool_context: ProjectToolContext,
        active_contract: ToolSpec | None,
        messages: list[dict[str, str]],
    ) -> str:
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
            self.tool_runtime.maybe_capture_contract_implementation(
                messages=messages,
                response_text="",
                active_contract=active_contract,
                trace_id=trace_id,
            )
            self.tool_runtime.record_contract_outcome(
                tool_spec=active_contract,
                project_id=tool_context.project_id,
                success=False,
                notes="max_steps_timeout",
                trace_id=trace_id,
            )
            self._reload_tool_runtime_state()

        self.working_memory.add_message("assistant", timeout_response)
        return self._finalize_trace(
            status="timeout",
            reply=timeout_response,
            route="timeout",
            model_name="loop_guard",
        )

    def _finalize_direct_skill_call(
        self,
        *,
        user_input: str,
        direct_skill_call: DirectSkillCall,
        trace_id: str,
        related_memories: list[str],
        tool_context: ProjectToolContext,
        loop_compactor: LoopContextCompactor,
        messages: list[dict[str, str]],
    ) -> dict[str, object]:
        observation = self._handle_action_step(
            action_name=direct_skill_call.tool_name,
            action_input=direct_skill_call.tool_input,
            trace_id=trace_id,
            tool_context=tool_context,
            loop_compactor=loop_compactor,
            messages=messages,
        )
        return self._finalize_success(
            user_input=user_input,
            response=f"Final Answer: {observation}",
            final_answer=observation,
            trace_id=trace_id,
            related_memories=related_memories,
            tool_steps=1,
            tool_context=tool_context,
            active_contract=None,
            loop_compactor=loop_compactor,
            messages=messages,
            route="deterministic_skill_router",
            model_name=direct_skill_call.reason,
        )

    @staticmethod
    def _new_trace_id() -> str:
        return f"tr_{uuid.uuid4().hex}"

    def _executable_tool_names(self) -> set[str]:
        names = set(self.skill_manager.list_skills())
        if hasattr(self.tools, "registry"):
            names.update(getattr(self.tools.registry, "_tools", {}).keys())
        return names

    def _record_trace_candidates(
        self,
        *,
        skill_candidates: list[SkillCandidate],
        tool_matches: list[ToolMatchResult],
    ) -> None:
        if self._active_trace is None:
            return
        self._active_trace.set_candidates(
            skill_candidates=skill_candidates,
            tool_matches=tool_matches,
        )

    def _record_trace_step(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        if self._active_trace is None:
            return
        self._active_trace.add_step(
            kind=kind,
            title=title,
            content=content,
            metadata=metadata,
        )

    def _record_rl_policy_suggestion(
        self,
        *,
        user_input: str,
        skill_candidates: list[SkillCandidate],
        tool_matches: list[ToolMatchResult],
    ) -> PolicySuggestion:
        suggestion = self.rl_runtime_router.suggest(
            user_input=user_input,
            skill_candidates=[
                {"name": item.name, "score": item.score}
                for item in skill_candidates
            ],
            tool_matches=[
                {"name": item.spec.name, "score": item.breakdown.total_score}
                for item in tool_matches
            ],
            steps=[],
            route_hint="pre_loop",
        )
        self._record_trace_step(
            kind="policy",
            title="RL Policy Suggestion",
            content=(
                f"action={suggestion.action.value} "
                f"confidence={suggestion.confidence:.4f} "
                f"rationale={suggestion.rationale}"
            ),
            metadata={"scores": suggestion.scores},
        )
        return suggestion

    def _apply_rl_policy_gate(
        self,
        *,
        suggestion: PolicySuggestion,
        user_input: str,
        tool_matches: list[ToolMatchResult],
    ) -> DirectSkillCall | None:
        if not self.config.agent.rl_gate_enabled:
            return None
        if suggestion.confidence < self.config.agent.rl_gate_min_confidence:
            return None

        if suggestion.action is DecisionAction.DIRECT_TOOL:
            direct_skill_call = SkillRouter.infer_direct_skill_call(
                user_input=user_input,
                tool_matches=tool_matches,
                executable_tool_names=self._executable_tool_names(),
                allow_policy_override=True,
            )
            if direct_skill_call is None:
                return None
            self._record_trace_step(
                kind="policy_gate",
                title="RL Policy Gate",
                content="Applied direct_tool gate before the main loop.",
                metadata={
                    "action": suggestion.action.value,
                    "confidence": suggestion.confidence,
                },
            )
            return DirectSkillCall(
                tool_name=direct_skill_call.tool_name,
                tool_input=direct_skill_call.tool_input,
                reason="rl_policy_gate",
                matched_via=direct_skill_call.matched_via,
            )

        if suggestion.action is DecisionAction.BUILD_TOOL:
            self._active_rl_gate_note = (
                "[RL Decision Gate]\n"
                "Policy suggests: prefer emitting a Tool Spec before extra tool exploration."
            )
        elif suggestion.action is DecisionAction.ASK_TEACHER:
            self._active_rl_gate_note = (
                "[RL Decision Gate]\n"
                "Policy suggests: if the first Tool Spec is incomplete or the tool path stalls, ask the teacher early."
            )
        else:
            return None

        self._record_trace_step(
            kind="policy_gate",
            title="RL Policy Gate",
            content=self._active_rl_gate_note,
            metadata={
                "action": suggestion.action.value,
                "confidence": suggestion.confidence,
            },
        )
        return None

    def _compose_loop_brief(self, base_brief: str) -> str:
        if not self._active_rl_gate_note:
            return base_brief
        if not base_brief.strip():
            return self._active_rl_gate_note
        return f"{base_brief}\n\n{self._active_rl_gate_note}"

    def _expand_direct_route_candidates(
        self,
        *,
        user_input: str,
        tool_context: ProjectToolContext,
        initial_matches: list[ToolMatchResult],
    ) -> list[ToolMatchResult]:
        if not any(hint in user_input.lower() for hint in ("直接调用", "现有工具", "please call", "use existing tool")):
            return initial_matches
        if any(match.spec.name in self._executable_tool_names() for match in initial_matches):
            return initial_matches
        expanded_top_k = max(8, len(self._executable_tool_names()) + 3)
        return self.tool_discovery.recommend(tool_context, top_k=expanded_top_k)

    def _finalize_trace(
        self,
        *,
        status: str,
        reply: str,
        route: str,
        model_name: str,
    ) -> dict[str, object]:
        self._record_trace_step(
            kind="final",
            title="Final Result",
            content=reply,
            metadata={"status": status, "route": route, "model_name": model_name},
        )
        if self._active_trace is None:
            return {
                "trace_id": "",
                "user_input": "",
                "status": status,
                "route": route,
                "model_name": model_name,
                "reply": reply,
                "skill_candidates": [],
                "tool_matches": [],
                "steps": [],
            }
        payload = self._active_trace.finalize(
            status=status,
            reply=reply,
            route=route,
            model_name=model_name,
        )
        self._active_trace = None
        self._active_rl_gate_note = ""
        return payload

    def _refresh_system_prompt(
        self,
        mood: str,
        memories: list[str],
        skill_candidates: list[SkillCandidate],
        tool_context: ProjectToolContext,
        tool_matches: list[ToolMatchResult],
        loop_brief: str,
    ) -> None:
        prompt = self.prompt_builder.build(
            mood=mood,
            tool_desc=self.tools.get_tool_desc(),
            memories=memories,
            skill_candidates=skill_candidates,
            tool_context=tool_context,
            tool_matches=tool_matches,
            loop_brief=loop_brief,
        )
        self.working_memory.replace_system_prompt(prompt)

    def _reload_tool_runtime_state(self) -> None:
        self.tool_knowledge_base = self.tool_runtime.build_tool_knowledge_base()
        self.tool_discovery = ToolDiscoveryEngine(self.tool_knowledge_base)

    def _try_evolve(
        self,
        messages: list[dict[str, str]],
        user_input: str,
        response_text: str,
        trace_id: str,
        protected_skill_names: tuple[str, ...] = (),
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

        candidates.extend(self.tool_runtime.collect_code_candidates(response_text))

        seen: set[str] = set()
        for candidate_code in candidates:
            normalized = candidate_code.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            validation = self.skill_manager.validate(normalized)
            if validation.is_valid and validation.function_name:
                if validation.function_name in protected_skill_names:
                    self.skill_event_logger.log(
                        "skill_internalize_deferred",
                        trace_id,
                        {"skill_name": validation.function_name, "reason": "contract_managed"},
                    )
                    continue
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
