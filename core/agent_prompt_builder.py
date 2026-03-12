"""System-prompt composition for the agent runtime."""

from __future__ import annotations

from pathlib import Path

import yaml

from config.settings import AppConfig
from skills.selector import SkillCandidate
from skills.tool_contracts import (
    HelpRequestKind,
    ProjectToolContext,
    ToolFailureRecord,
    ToolMatchResult,
)
from skills.tool_escalation import TeacherEscalationPlanner


class AgentPromptBuilder:
    """Build the agent system prompt from stable runtime facts."""

    def __init__(
        self,
        *,
        config: AppConfig,
        teacher_escalation: TeacherEscalationPlanner,
    ) -> None:
        self.config = config
        self.teacher_escalation = teacher_escalation
        self.prompts = self._load_prompts()

    def build(
        self,
        *,
        mood: str,
        tool_desc: str,
        memories: list[str],
        skill_candidates: list[SkillCandidate],
        tool_context: ProjectToolContext,
        tool_matches: list[ToolMatchResult],
        loop_brief: str,
    ) -> str:
        template = self.prompts.get("system_persona", self._default_system_template())
        memories_text = (
            "\n".join(f"- {item}" for item in memories)
            if memories
            else "[暂无相关记忆]"
        )
        base_prompt = template.format(
            mood=mood,
            tool_desc=tool_desc,
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
        return self._append_execution_brief_instruction(
            prompt=prompt,
            loop_brief=loop_brief,
        )

    @staticmethod
    def _load_prompts() -> dict:
        prompt_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
        if not prompt_path.exists():
            return {"system_persona": AgentPromptBuilder._default_system_template()}

        with prompt_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "system_persona" not in data:
            data["system_persona"] = AgentPromptBuilder._default_system_template()
        return data

    @staticmethod
    def _default_system_template() -> str:
        return (
            "你是 CoALA Agent，负责协调记忆、工具和技能完成任务。\n"
            "当前情绪: {mood}\n\n"
            "[可用工具]\n{tool_desc}\n\n"
            "[相关记忆]\n{memories}\n\n"
            "请始终按照 ReAct 格式推理：\n"
            "Thought: ...\n"
            "Action: <tool_name>\n"
            "Action Input: <tool_input>\n"
            "Observation: <tool_output>\n"
            "Final Answer: <answer>\n"
        )

    def _append_language_instruction(self, prompt: str) -> str:
        language = self.config.agent.response_language.strip().lower()
        if language in {"zh", "zh-cn", "zh-hans", "chinese"}:
            return (
                f"{prompt}\n\n"
                "[语言要求]\n"
                "1. 默认使用简体中文回答，除非用户明确要求其他语言。\n"
                "2. 术语、代码、路径、变量名保持原样，不要强行翻译。\n"
                "3. 需要英文关键字时，先给结论，再保留关键英文标识。\n"
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
            "优先考虑复用已有技能；如果技能不匹配，再考虑 `python_repl` 或新建 Tool Spec。",
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
            "策略: 先复用，再定义 Tool Spec，再在受阻时向大模型发结构化求助。",
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
                    "[工具构建要求]",
                    "如果没有合适工具，先输出一个 fenced ```tool_spec``` JSON。",
                    "Tool Spec 至少包含: name, purpose, inputs, outputs, side_effects, failure_modes, examples。",
                    "如果自己无法补全，再按结构化方式向大模型求助。",
                    f"求助类型: {teacher_request.kind.value}",
                    f"期望返回: {teacher_request.requested_output}",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _append_execution_brief_instruction(*, prompt: str, loop_brief: str) -> str:
        if not loop_brief.strip():
            return prompt
        return f"{prompt}\n\n{loop_brief}"
