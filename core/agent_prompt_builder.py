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
        memories_text = "\n".join(f"- {item}" for item in memories) if memories else "[无相关记忆]"
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
            "你是 CoALA Agent。你的目标是稳定完成任务，而不是展示冗长思考。\n"
            "当前情绪状态: {mood}\n\n"
            "[可用工具]\n{tool_desc}\n\n"
            "[相关记忆]\n{memories}\n\n"
            "[输出协议]\n"
            "每次回复只能选择以下三种格式之一，不要混用：\n"
            "1. 工具调用:\n"
            "Thought: <一句简短理由>\n"
            "Action: <tool_name>\n"
            "Action Input: <tool_input>\n"
            "2. 工具契约:\n"
            "```tool_spec\n"
            "{{\"name\":\"...\",\"purpose\":\"...\",\"inputs\":[...],\"outputs\":[...],"
            "\"side_effects\":[...],\"failure_modes\":[...],\"examples\":[...]}}\n"
            "```\n"
            "3. 最终答复:\n"
            "Final Answer: <answer>\n"
        )

    def _append_language_instruction(self, prompt: str) -> str:
        language = self.config.agent.response_language.strip().lower()
        if language in {"zh", "zh-cn", "zh-hans", "chinese"}:
            return (
                f"{prompt}\n\n"
                "[执行约束]\n"
                "1. 优先复用已有工具；仅在确认没有合适工具时再定义 Tool Spec。\n"
                "2. 每轮最多调用一个工具，不要在同一条消息里输出多个 Action。\n"
                "3. Tool Spec 必须输出为 fenced ```tool_spec``` JSON，不要写自然语言伪 JSON。\n"
                "4. 收到确定性 Observation 后，如果已经足够回答用户，就直接输出 Final Answer。\n"
                "5. 不要重复输出相同的 Action、相同的 Tool Spec 或相同的解释。\n"
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
            "[候选技能]",
            "下面是当前任务最相关的已有技能。若其中某个技能能直接完成任务，应优先调用它，不要改写为其他工具名。",
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
            "[工具生命周期上下文]",
            f"当前任务: {tool_context.task_summary or '(empty)'}",
            "规则: 先判断已有工具是否匹配当前任务的目标、输入、输出；只有在确实缺失时才定义新的 Tool Spec。",
        ]

        if tool_context.existing_tools:
            lines.append(f"现有工具: {', '.join(tool_context.existing_tools)}")
        else:
            lines.append("现有工具: (none)")

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
                    "[缺少合适工具时的要求]",
                    "请输出 fenced ```tool_spec``` JSON。",
                    "Tool Spec 至少必须包含: name, purpose, inputs, outputs, side_effects, failure_modes, examples。",
                    "如果你无法补全这些字段，请先输出不完整 Tool Spec，让系统向大模型请求修复。",
                    f"必要时的求助类型: {teacher_request.kind.value}",
                    f"期望求助输出: {teacher_request.requested_output}",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _append_execution_brief_instruction(*, prompt: str, loop_brief: str) -> str:
        if not loop_brief.strip():
            return prompt
        return f"{prompt}\n\n{loop_brief}"
