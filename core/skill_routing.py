"""Deterministic skill-routing helpers driven by ToolSpec contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills.tool_contracts import ToolIOField, ToolMatchResult, ToolSpec


@dataclass(frozen=True)
class DirectSkillCall:
    """A high-confidence tool call inferred without another LLM turn."""

    tool_name: str
    tool_input: str
    reason: str
    matched_via: str


class SkillRouter:
    """Apply contract-aware deterministic routing when the request is explicit."""

    _INT_PATTERN = re.compile(r"-?\d+")
    _FLOAT_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
    _PATH_PATTERN = re.compile(r"([A-Za-z]:\\[^\s\"']+|(?:\.{0,2}/)?[\w./-]+)")
    _QUOTED_PATTERN = re.compile(r"[\"'“”‘’]([^\"'“”‘’]+)[\"'“”‘’]")
    _WORD_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]*\b")
    _RANGE_PATTERN = re.compile(r"1\s*(?:到|至|-)\s*(\d+)")
    _DIRECT_HINTS = (
        "直接调用",
        "直接使用",
        "调用现有工具",
        "用现有工具",
        "please call",
        "use existing tool",
    )
    _RESULT_ONLY_HINTS = (
        "只返回结果",
        "只给结果",
        "直接给结果",
        "only return the result",
    )
    _PATH_FIELD_NAMES = {
        "path",
        "repo_path",
        "project_path",
        "root_path",
        "workspace_path",
        "file_path",
        "filename",
        "name",
    }
    _REQUEST_FIELD_NAMES = {"user_request", "request", "query", "prompt", "instruction"}
    _TEXT_FIELD_NAMES = {"text", "content", "message", "keyword", "pattern"}
    _LIKELY_INT_FIELD_NAMES = {"n", "count", "index", "a", "b", "x", "y", "num", "number"}
    _INT_TYPES = {"int", "integer", "number"}
    _FLOAT_TYPES = {"float", "double"}
    _TOP_MATCH_MIN_SCORE = 2.0
    _TOP_MATCH_MARGIN = 0.75
    _AUTO_ROUTE_MIN_SCORE = 4.5
    _AUTO_ROUTE_TAGS = {"deterministic_builtin"}
    _DOCUMENT_SUMMARY_HINTS = (
        "文档摘要",
        "文件摘要",
        "目录摘要",
        "整体摘要",
        "全局摘要",
        "semantic summary",
        "global summary",
        "summarize documents",
        "read folder",
        "读取文件夹",
        "读取文档",
        "pdf",
        "docx",
        "excel",
        "xlsx",
    )

    @classmethod
    def infer_direct_skill_call(
        cls,
        *,
        user_input: str,
        tool_matches: list[ToolMatchResult],
        executable_tool_names: set[str],
        allow_policy_override: bool = False,
    ) -> DirectSkillCall | None:
        normalized = user_input.strip().lower()
        if not normalized:
            return None

        document_summary_call = cls._infer_document_summary_route(
            user_input=user_input,
            tool_matches=tool_matches,
            executable_tool_names=executable_tool_names,
        )
        if document_summary_call is not None:
            return document_summary_call

        executable_matches = [
            item for item in tool_matches if item.spec.name in executable_tool_names
        ]
        if not executable_matches:
            return None

        top_match = executable_matches[0]
        if top_match.breakdown.total_score < cls._TOP_MATCH_MIN_SCORE:
            return None
        if len(executable_matches) > 1:
            margin = top_match.breakdown.total_score - executable_matches[1].breakdown.total_score
            if margin < cls._TOP_MATCH_MARGIN:
                return None

        has_direct_hint = any(hint in normalized for hint in cls._DIRECT_HINTS)
        has_auto_route_tag = bool(cls._AUTO_ROUTE_TAGS & set(top_match.spec.tags))
        if not has_direct_hint:
            if not allow_policy_override and not has_auto_route_tag:
                return None
            if not allow_policy_override and top_match.breakdown.total_score < cls._AUTO_ROUTE_MIN_SCORE:
                return None

        bound_input = cls._bind_tool_input(user_input=user_input, spec=top_match.spec)
        if bound_input is None:
            return None

        return DirectSkillCall(
            tool_name=top_match.spec.name,
            tool_input=bound_input,
            reason="tool_spec_direct_route" if has_direct_hint else "deterministic_builtin_auto_route",
            matched_via=top_match.rationale,
        )

    @classmethod
    def _infer_document_summary_route(
        cls,
        *,
        user_input: str,
        tool_matches: list[ToolMatchResult],
        executable_tool_names: set[str],
    ) -> DirectSkillCall | None:
        lowered = user_input.strip().lower()
        if not any(hint in lowered for hint in cls._DOCUMENT_SUMMARY_HINTS):
            return None

        preferred_name = "summarize_documents_semantic" if any(
            token in lowered for token in ("semantic", "主题", "全局", "整体")
        ) else "summarize_documents"

        for name in (preferred_name, "summarize_documents", "summarize_documents_semantic"):
            if name not in executable_tool_names:
                continue
            match = next((item for item in tool_matches if item.spec.name == name), None)
            if match is None:
                continue
            bound_input = cls._bind_tool_input(user_input=user_input, spec=match.spec)
            if bound_input is None:
                continue
            return DirectSkillCall(
                tool_name=name,
                tool_input=bound_input,
                reason="document_summary_auto_route",
                matched_via=match.rationale,
            )
        return None

    @classmethod
    def should_finalize_from_observation(
        cls,
        *,
        user_input: str,
        action_name: str,
        observation: str,
    ) -> bool:
        normalized = user_input.strip().lower()
        if not observation.strip():
            return False
        lowered_observation = observation.strip().lower()
        if "error" in lowered_observation or "not found" in lowered_observation:
            return False
        if any(hint in normalized for hint in cls._RESULT_ONLY_HINTS):
            return True
        return action_name in {"calc_sum_n", "calc_lcm", "fibonacci"} and len(observation) <= 80

    @classmethod
    def _bind_tool_input(cls, *, user_input: str, spec: ToolSpec) -> str | None:
        if not spec.inputs:
            return ""

        remaining_ints = cls._INT_PATTERN.findall(user_input)
        remaining_floats = cls._FLOAT_PATTERN.findall(user_input)
        args: list[str] = []

        for field in spec.inputs:
            bound = cls._extract_field_binding(
                user_input=user_input,
                field=field,
                remaining_ints=remaining_ints,
                remaining_floats=remaining_floats,
            )
            if bound is None:
                if field.required:
                    return None
                continue
            args.append(bound)

        return ", ".join(args)

    @classmethod
    def _extract_field_binding(
        cls,
        *,
        user_input: str,
        field: ToolIOField,
        remaining_ints: list[str],
        remaining_floats: list[str],
    ) -> str | None:
        field_name = field.name.strip().lower()
        field_type = field.type_name.strip().lower()
        normalized = user_input.strip()
        normalized_lower = normalized.lower()

        if field_name in cls._REQUEST_FIELD_NAMES:
            return repr(normalized)

        if field_name in cls._PATH_FIELD_NAMES:
            if any(token in normalized_lower for token in ("当前项目", "current project", "this project")):
                return repr(".")
            quoted = cls._QUOTED_PATTERN.search(normalized)
            if quoted:
                return repr(quoted.group(1))
            path_match = cls._PATH_PATTERN.search(normalized)
            if path_match:
                return repr(path_match.group(1))
            return None

        if field_type in cls._INT_TYPES:
            if field_name == "n":
                range_match = cls._RANGE_PATTERN.search(normalized_lower)
                if range_match:
                    return range_match.group(1)
            if remaining_ints:
                return remaining_ints.pop(0)
            return None

        if field_name in cls._LIKELY_INT_FIELD_NAMES and remaining_ints:
            if field_name == "n":
                range_match = cls._RANGE_PATTERN.search(normalized_lower)
                if range_match:
                    return range_match.group(1)
            return remaining_ints.pop(0)

        if field_type in cls._FLOAT_TYPES:
            if remaining_floats:
                return remaining_floats.pop(0)
            return None

        if field_name in cls._TEXT_FIELD_NAMES or field_type in {"str", "string", "text"}:
            quoted = cls._QUOTED_PATTERN.search(normalized)
            if quoted:
                return repr(quoted.group(1))
            if field_name == "name":
                words = [
                    item
                    for item in cls._WORD_PATTERN.findall(normalized)
                    if item.lower() not in {"please", "call", "tool", "result", "use", "existing"}
                ]
                if words:
                    return repr(words[-1])
            return repr(normalized)

        return None
