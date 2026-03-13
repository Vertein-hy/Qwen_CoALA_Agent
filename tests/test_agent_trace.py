from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import sys
import types

if importlib.util.find_spec("ollama") is None:
    ollama_stub = types.ModuleType("ollama")

    class _DummyClient:
        def __init__(self, host: str) -> None:
            self.host = host

    ollama_stub.Client = _DummyClient
    sys.modules["ollama"] = ollama_stub

if importlib.util.find_spec("chromadb") is None:
    chromadb_stub = types.ModuleType("chromadb")
    chromadb_utils_stub = types.ModuleType("chromadb.utils")
    embedding_stub = types.ModuleType("chromadb.utils.embedding_functions")

    class _DefaultEmbeddingFunction:
        def __call__(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] for _ in texts]

    embedding_stub.DefaultEmbeddingFunction = _DefaultEmbeddingFunction
    chromadb_utils_stub.embedding_functions = embedding_stub
    chromadb_stub.utils = chromadb_utils_stub

    sys.modules["chromadb"] = chromadb_stub
    sys.modules["chromadb.utils"] = chromadb_utils_stub
    sys.modules["chromadb.utils.embedding_functions"] = embedding_stub

from config.settings import AgentConfig, AppConfig, SkillConfig
from core.agent import CognitiveAgent
from core.contracts import ChatResult
from modules.tools import ToolBox
from skills.manager import SkillManager
from skills.tool_registry import ToolRegistry


class FakeMemory:
    def __init__(self) -> None:
        self.search_trace_ids: list[str | None] = []
        self.add_trace_ids: list[str | None] = []
        self.add_write_reasons: list[str | None] = []

    def search(
        self,
        query: str,
        n_results: int = 3,
        trace_id: str | None = None,
        query_type: str = "default",
    ) -> dict:
        self.search_trace_ids.append(trace_id)
        return {"documents": [], "memory_ids": [], "distances": [], "query_id": "q_test"}

    def add(
        self,
        text: str,
        metadata: dict | None = None,
        trace_id: str | None = None,
        write_reason: str | None = None,
        source: str = "self_generated",
        score_snapshot: dict | None = None,
    ) -> str:
        self.add_trace_ids.append(trace_id)
        self.add_write_reasons.append(write_reason)
        return "mem_test"


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute(self, tool_name: str, tool_input: str) -> str:
        self.calls.append((tool_name, tool_input))
        if tool_name == "calc_sum_n":
            n = int(tool_input.strip())
            return str(sum(range(1, n + 1)))
        return "ok"

    @staticmethod
    def get_tool_desc() -> str:
        return "noop: no operation"


class FakeEmotionEngine:
    current_mood = "Neutral"

    @staticmethod
    def update_mood(user_input: str, recent_memories: list[str]) -> str:
        return "Neutral"


class FakeEvolver:
    @staticmethod
    def evolve(user_intent: str, successful_code: str) -> None:
        return None


@dataclass
class FinalAnswerLLM:
    response: str = "Final Answer: done"

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        return ChatResult(content=self.response, model_name="fake-model", route="fake-route")


@dataclass
class ToolLoopLLM:
    response: str = "Thought: keep going\nAction: noop\nAction Input: test"

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        return ChatResult(content=self.response, model_name="fake-model", route="fake-route")


@dataclass
class CodeAnswerLLM:
    response: str = (
        "```python\n"
        "def auto_sum_n(n):\n"
        '    """Return sum from 1 to n."""\n'
        "    return sum(range(1, n + 1))\n"
        "```\n"
        "Final Answer: tool extracted"
    )

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        return ChatResult(content=self.response, model_name="fake-model", route="fake-route")


@dataclass
class ToolLifecycleLLM:
    small_responses: list[str] = field(
        default_factory=lambda: [
            """```tool_spec
{"name":"draft_sum_tool","purpose":"","inputs":[{"name":"n","type_name":"int"}],"outputs":[{"name":"result","type_name":"int"}]}
```""",
            "Final Answer: tool ready",
        ]
    )
    large_responses: list[str] = field(
        default_factory=lambda: [
            """```tool_spec
{"name":"draft_sum_tool","purpose":"Return the sum from 1 to n.","inputs":[{"name":"n","type_name":"int","required":true}],"outputs":[{"name":"result","type_name":"int","required":true}],"failure_modes":["invalid_n"],"examples":["n=5 -> 15"]}
```
Repair complete."""
        ]
    )
    large_calls: int = 0

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        if route_hint == "large":
            self.large_calls += 1
            return ChatResult(
                content=self.large_responses.pop(0),
                model_name="large-model",
                route="forced_large",
            )
        return ChatResult(
            content=self.small_responses.pop(0),
            model_name="small-model",
            route="forced_small",
        )


@dataclass
class ContextCompressionLLM:
    responses: list[str] = field(
        default_factory=lambda: [
            "Thought: step 1\nAction: noop\nAction Input: scan workspace",
            "Thought: step 2\nAction: noop\nAction Input: inspect contract",
            "Thought: step 3\nAction: noop\nAction Input: re-check latest observation",
            "Final Answer: done",
        ]
    )
    seen_messages: list[list[dict[str, str]]] = field(default_factory=list)

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        self.seen_messages.append([dict(item) for item in messages])
        return ChatResult(
            content=self.responses.pop(0),
            model_name="small-model",
            route="forced_small",
        )


@dataclass
class GlobalPromotionLLM:
    small_responses: list[str] = field(
        default_factory=lambda: [
            """```tool_spec
{"name":"draft_sum_tool","purpose":"","inputs":[{"name":"n","type_name":"int"}],"outputs":[{"name":"result","type_name":"int"}]}
```""",
            (
                "```python\n"
                "def draft_sum_tool(n):\n"
                '    """Return the sum from 1 to n."""\n'
                "    return sum(range(1, n + 1))\n"
                "```\n"
                "Final Answer: tool ready"
            ),
        ]
    )
    large_responses: list[str] = field(
        default_factory=lambda: [
            """```tool_spec
{"name":"draft_sum_tool","purpose":"Return the sum from 1 to n.","inputs":[{"name":"n","type_name":"int","required":true}],"outputs":[{"name":"result","type_name":"int","required":true}],"failure_modes":["invalid_n"],"examples":["n=5 -> 15"]}
```
Repair complete."""
        ]
    )

    def chat_with_meta(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        route_hint: str = "auto",
    ) -> ChatResult:
        if route_hint == "large":
            return ChatResult(
                content=self.large_responses.pop(0),
                model_name="large-model",
                route="forced_large",
            )
        return ChatResult(
            content=self.small_responses.pop(0),
            model_name="small-model",
            route="forced_small",
        )


def _build_agent(
    llm: object,
    memory: FakeMemory,
    max_steps: int = 3,
    skill_manager: SkillManager | None = None,
    config: AppConfig | None = None,
    tool_registry: ToolRegistry | None = None,
    tools: FakeTools | None = None,
) -> CognitiveAgent:
    cfg = config or AppConfig(
        agent=AgentConfig(max_steps=max_steps, memory_top_k=3, default_temperature=0.1),
        skills=SkillConfig(enable_event_log=False),
    )
    return CognitiveAgent(
        config=cfg,
        llm=llm,  # type: ignore[arg-type]
        long_term_memory=memory,  # type: ignore[arg-type]
        tools=tools or FakeTools(),  # type: ignore[arg-type]
        emotion_engine=FakeEmotionEngine(),  # type: ignore[arg-type]
        evolver=FakeEvolver(),  # type: ignore[arg-type]
        skill_manager=skill_manager,
        tool_registry=tool_registry,
    )


def test_trace_id_is_shared_between_search_and_add_on_final_answer() -> None:
    memory = FakeMemory()
    agent = _build_agent(llm=FinalAnswerLLM(), memory=memory)

    answer = agent.run("hello")

    assert answer == "done"
    assert len(memory.search_trace_ids) == 1
    assert len(memory.add_trace_ids) == 1
    assert memory.search_trace_ids[0] == memory.add_trace_ids[0]
    assert memory.search_trace_ids[0] is not None
    assert memory.search_trace_ids[0].startswith("tr_")


def test_timeout_path_still_writes_memory_with_same_trace_id() -> None:
    memory = FakeMemory()
    agent = _build_agent(llm=ToolLoopLLM(), memory=memory, max_steps=2)

    answer = agent.run("keep calling tools")

    assert isinstance(answer, str)
    assert answer
    assert len(memory.search_trace_ids) == 1
    assert len(memory.add_trace_ids) == 1
    assert memory.search_trace_ids[0] == memory.add_trace_ids[0]
    assert memory.add_write_reasons[0] in {"max_steps_timeout", "fallback_response"}


def test_system_prompt_contains_tool_lifecycle_context() -> None:
    memory = FakeMemory()
    agent = _build_agent(llm=FinalAnswerLLM(), memory=memory)

    _ = agent.run("need a new repository tool")
    system_prompt = agent.working_memory.get_context()[0]["content"]

    assert "Tool Spec" in system_prompt
    assert "need a new repository tool" in system_prompt


def test_system_prompt_includes_ranked_skill_candidates(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    skill_manager.append_skill(
        source="sum numbers from 1 to n",
        function_code="""
def calc_sum_n(n):
    \"\"\"Return sum from 1 to n.\"\"\"
    return sum(range(1, n + 1))
        """,
    )

    memory = FakeMemory()
    agent = _build_agent(
        llm=FinalAnswerLLM(),
        memory=memory,
        skill_manager=skill_manager,
    )

    _ = agent.run("sum numbers from 1 to 100")
    system_prompt = agent.working_memory.get_context()[0]["content"]

    assert "calc_sum_n" in system_prompt
    assert "score=" in system_prompt


def test_agent_internalizes_skill_from_plain_code_block_response(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    memory = FakeMemory()
    agent = _build_agent(
        llm=CodeAnswerLLM(),
        memory=memory,
        skill_manager=skill_manager,
    )

    _ = agent.run("write a helper that sums integers")

    assert skill_manager.has_skill("auto_sum_n")


def test_agent_requests_teacher_help_for_incomplete_tool_spec(tmp_path) -> None:
    memory = FakeMemory()
    llm = ToolLifecycleLLM()
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    tool_registry = ToolRegistry(index_file=tmp_path / "tool_registry.json")
    agent = _build_agent(
        llm=llm,
        memory=memory,
        max_steps=4,
        skill_manager=skill_manager,
        tool_registry=tool_registry,
    )

    answer = agent.run("design a sum tool")

    assert answer == "tool ready"
    assert llm.large_calls == 1
    record = tool_registry.get_record("draft_sum_tool")
    assert record is not None
    assert record.origin == "teacher"
    assert record.tier.value in {"episode", "project"}
    assert tool_registry.executions_for("draft_sum_tool")


def test_agent_compacts_loop_context_for_small_models() -> None:
    memory = FakeMemory()
    llm = ContextCompressionLLM()
    config = AppConfig(
        agent=AgentConfig(
            max_steps=4,
            memory_top_k=3,
            default_temperature=0.1,
            compact_history_trigger=4,
            keep_recent_messages=2,
        ),
        skills=SkillConfig(enable_event_log=False),
    )
    agent = _build_agent(llm=llm, memory=memory, config=config)

    answer = agent.run("finish a long multi-step task without losing the goal")

    assert answer == "done"
    assert any(
        any("[Compressed Loop History]" in msg["content"] for msg in call)
        for call in llm.seen_messages
    )
    last_system = llm.seen_messages[-1][0]["content"]
    assert "[Execution Brief]" in last_system
    assert "finish a long multi-step task without losing the goal" in last_system


def test_global_promotion_internalizes_tool_after_repeated_success(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    tool_registry = ToolRegistry(index_file=tmp_path / "tool_registry.json")

    def _run(project_id: str) -> str:
        config = AppConfig(
            agent=AgentConfig(
                project_id=project_id,
                max_steps=4,
                memory_top_k=3,
                default_temperature=0.1,
            ),
            skills=SkillConfig(enable_event_log=False),
        )
        agent = _build_agent(
            llm=GlobalPromotionLLM(),
            memory=FakeMemory(),
            config=config,
            skill_manager=skill_manager,
            tool_registry=tool_registry,
        )
        return agent.run(f"design a reusable sum tool for {project_id}")

    assert _run("proj-alpha") == "tool ready"
    assert _run("proj-alpha") == "tool ready"
    assert _run("proj-beta") == "tool ready"

    record = tool_registry.get_record("draft_sum_tool")
    assert record is not None
    assert record.tier.value == "global"
    assert record.implementation_code.strip().startswith("def draft_sum_tool")
    assert skill_manager.has_skill("draft_sum_tool")


def test_direct_skill_router_executes_high_confidence_existing_skill(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    skill_manager.append_skill(
        source="sum numbers from 1 to n",
        function_code="""
def calc_sum_n(n):
    return sum(range(1, n + 1))
        """,
    )
    tools = FakeTools()
    memory = FakeMemory()
    agent = _build_agent(
        llm=FinalAnswerLLM(),
        memory=memory,
        skill_manager=skill_manager,
        tools=tools,
    )

    answer = agent.run("请直接调用现有工具计算 1 到 10 的整数和，只返回结果。")

    assert answer == "55"
    assert tools.calls == [("calc_sum_n", "10")]


def test_direct_skill_router_binds_toolspec_path_input(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    skill_manager.append_skill(
        source="inspect current project path",
        function_code="""
def inspect_repo(repo_path):
    return repo_path
        """,
    )
    tools = FakeTools()
    memory = FakeMemory()
    agent = _build_agent(
        llm=FinalAnswerLLM(),
        memory=memory,
        skill_manager=skill_manager,
        tools=tools,
    )

    answer = agent.run("请直接调用现有工具检查当前项目路径，只返回结果。")

    assert answer == "ok"
    assert tools.calls == [("inspect_repo", "'.'")]


def test_repeated_same_response_stops_before_max_steps() -> None:
    memory = FakeMemory()
    agent = _build_agent(llm=ToolLoopLLM(), memory=memory, max_steps=5)

    answer = agent.run("keep calling tools")

    assert "重复输出相同内容" in answer
    assert memory.add_write_reasons[0] == "fallback_response"


def test_run_with_trace_exposes_action_observation_and_final(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    skill_manager.append_skill(
        source="sum numbers from 1 to n",
        function_code="""
def calc_sum_n(n):
    return sum(range(1, n + 1))
        """,
    )
    tools = FakeTools()
    memory = FakeMemory()
    agent = _build_agent(
        llm=FinalAnswerLLM(),
        memory=memory,
        skill_manager=skill_manager,
        tools=tools,
    )

    trace = agent.run_with_trace("请直接调用现有工具计算 1 到 10 的整数和，只返回结果。")

    assert trace["reply"] == "55"
    step_kinds = [item["kind"] for item in trace["steps"]]
    assert "direct_route" in step_kinds
    assert "action" in step_kinds
    assert "observation" in step_kinds
    assert "final" in step_kinds


def test_http_route_request_uses_deterministic_builtin_tool(tmp_path: Path) -> None:
    project_file = tmp_path / "api_app.py"
    project_file.write_text(
        "\n".join(
            [
                "from flask import Flask",
                "app = Flask(__name__)",
                "",
                "@app.get('/health')",
                "def health():",
                "    return {'status': 'ok'}",
            ]
        ),
        encoding="utf-8",
    )
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    tools = ToolBox(
        data_dir=str(tmp_path / "data"),
        skills_file=str(tmp_path / "custom_skills.py"),
    )
    memory = FakeMemory()
    agent = _build_agent(
        llm=FinalAnswerLLM(),
        memory=memory,
        skill_manager=skill_manager,
        tools=tools,  # type: ignore[arg-type]
    )

    current = Path.cwd()
    try:
        os.chdir(tmp_path)
        trace = agent.run_with_trace("请从当前项目代码中提取所有 HTTP API 路由，并输出 markdown 摘要。")
    finally:
        os.chdir(current)

    assert trace["route"] == "deterministic_skill_router"
    assert "# HTTP API Routes" in str(trace["reply"])
    assert "| GET | /health | health | api_app.py |" in str(trace["reply"])
    step_kinds = [item["kind"] for item in trace["steps"]]
    assert "direct_route" in step_kinds
    assert "action" in step_kinds
    assert "observation" in step_kinds
