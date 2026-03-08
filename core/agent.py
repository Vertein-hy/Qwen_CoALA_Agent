"""Cognitive agent orchestration.

This module focuses on workflow orchestration and delegates domain work to
specialized components (LLM, memory, tools, emotion, evolution).
"""

from __future__ import annotations

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
from skills.manager import SkillManager


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
    ):
        self.config = config or load_config()
        self.prompts = self._load_prompts()

        self.llm = llm or LLMInterface(self.config)
        self.working_memory = working_memory or WorkingMemory()
        self.long_term_memory = long_term_memory or MemorySystem(self.config.memory)
        self.tools = tools or ToolBox()
        self.emotion_engine = emotion_engine or EmotionEngine(self.llm)
        self.evolver = evolver or SkillEvolver(self.llm, SkillManager())
        self.scorer = RuleBasedScorer()

        self._refresh_system_prompt(mood=self.emotion_engine.current_mood, memories=[])

    def run(self, user_input: str) -> str:
        trace_id = self._new_trace_id()
        memory_result = self.long_term_memory.search(
            query=user_input,
            n_results=self.config.agent.memory_top_k,
            trace_id=trace_id,
            query_type="task_context",
        )
        related_memories = memory_result.get("documents", [])

        mood = self.emotion_engine.update_mood(user_input, related_memories)
        self._refresh_system_prompt(mood=mood, memories=related_memories)
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
                observation = self.tools.execute(action.tool_name, action.tool_input)
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
                self._try_evolve(messages=messages, user_input=user_input)
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

    def _refresh_system_prompt(self, mood: str, memories: list[str]) -> None:
        template = self.prompts.get("system_persona", self._default_system_template())
        memories_text = "\n".join(f"- {item}" for item in memories) if memories else "[暂无相关记忆]"
        base_prompt = template.format(
            mood=mood,
            tool_desc=self.tools.get_tool_desc(),
            memories=memories_text,
        )
        prompt = self._append_language_instruction(base_prompt)
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

    def _try_evolve(self, messages: list[dict[str, str]], user_input: str) -> None:
        candidate_code = None
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
                candidate_code = code
                break

        if candidate_code:
            self.evolver.evolve(user_intent=user_input, successful_code=candidate_code)
