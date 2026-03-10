from __future__ import annotations

from dataclasses import dataclass
import importlib.util
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
from skills.manager import SkillManager


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
    def execute(self, tool_name: str, tool_input: str) -> str:
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


def _build_agent(
    llm: object,
    memory: FakeMemory,
    max_steps: int = 2,
    skill_manager: SkillManager | None = None,
) -> CognitiveAgent:
    config = AppConfig(
        agent=AgentConfig(max_steps=max_steps, memory_top_k=3, default_temperature=0.1),
        skills=SkillConfig(enable_event_log=False),
    )
    return CognitiveAgent(
        config=config,
        llm=llm,  # type: ignore[arg-type]
        long_term_memory=memory,  # type: ignore[arg-type]
        tools=FakeTools(),  # type: ignore[arg-type]
        emotion_engine=FakeEmotionEngine(),  # type: ignore[arg-type]
        evolver=FakeEvolver(),  # type: ignore[arg-type]
        skill_manager=skill_manager,
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

    assert answer == "任务已停止：达到最大推理步数。"
    assert len(memory.search_trace_ids) == 1
    assert len(memory.add_trace_ids) == 1
    assert memory.search_trace_ids[0] == memory.add_trace_ids[0]
    assert memory.add_write_reasons[0] == "max_steps_timeout"


def test_system_prompt_contains_chinese_language_requirement() -> None:
    memory = FakeMemory()
    agent = _build_agent(llm=FinalAnswerLLM(), memory=memory)

    system_prompt = agent.working_memory.get_context()[0]["content"]

    assert "简体中文" in system_prompt


def test_system_prompt_includes_ranked_skill_candidates(tmp_path) -> None:
    skill_manager = SkillManager(
        skill_file=tmp_path / "custom_skills.py",
        index_file=tmp_path / "index.json",
    )
    skill_manager.append_skill(
        source="计算 1 到 n 的和",
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

    _ = agent.run("请帮我计算从1到100的和")
    system_prompt = agent.working_memory.get_context()[0]["content"]

    assert "[候选内部技能]" in system_prompt
    assert "calc_sum_n" in system_prompt
