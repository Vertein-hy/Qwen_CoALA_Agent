"""Cognitive agent orchestration.

This module focuses on workflow orchestration and delegates domain work to
specialized components (LLM, memory, tools, emotion, evolution).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import yaml

from config.settings import AppConfig, load_config
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

        self._refresh_system_prompt(
            mood=self.emotion_engine.current_mood,
            memories=[],
            skill_candidates=[],
        )

    def run(self, user_input: str) -> str:
        trace_id = self._new_trace_id()
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

        mood = self.emotion_engine.update_mood(user_input, related_memories)
        self._refresh_system_prompt(
            mood=mood,
            memories=related_memories,
            skill_candidates=skill_candidates,
        )
        self.working_memory.add_message("user", user_input)

        messages = self.working_memory.get_context()
        tool_steps = 0

        for _ in range(self.config.agent.max_steps):
            llm_result = self.llm.chat_with_meta(
                messages=messages,
                temperature=self.config.agent.default_temperature,
                route_hint="auto",
            )
            response = llm_result.content

            action = ReActParser.parse_action(response)
            if action:
                tool_steps += 1
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
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue

            final_answer = ReActParser.parse_final_answer(response)
            if final_answer:
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
        self.working_memory.add_message("assistant", timeout_response)
        return timeout_response

    def _refresh_system_prompt(
        self,
        mood: str,
        memories: list[str],
        skill_candidates: list[SkillCandidate],
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

    def _try_evolve(
        self,
        messages: list[dict[str, str]],
        user_input: str,
        response_text: str,
        trace_id: str,
    ) -> None:
        candidates: list[str] = []

        # Highest confidence source: explicit python_repl tool calls in ReAct traces.
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

        # Non-ReAct fallback: extract function code from plain assistant text.
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

            # If extracted code is not directly valid, try evolver refactor path.
            if any(token in normalized for token in ["def ", "for ", "while ", "import "]):
                ok = self.evolver.evolve(user_intent=user_input, successful_code=normalized)
                event_type = "skill_internalized_via_evolver" if ok else "skill_internalize_failed"
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

        # Markdown fenced blocks
        for block in re.findall(r"```(?:python)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE):
            candidate = block.strip()
            if "def " in candidate:
                out.append(candidate)

        if out:
            return out

        # Plain inline function definition fallback.
        marker = "def "
        idx = text.find(marker)
        if idx >= 0:
            out.append(text[idx:].strip())
        return out
