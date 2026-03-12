from __future__ import annotations

from apps.web_console.server import ConsoleState


class _FakeAgent:
    def run_with_trace(self, user_input: str) -> dict[str, object]:
        return {
            "trace_id": "tr_test",
            "user_input": user_input,
            "status": "success",
            "route": "fake",
            "model_name": "fake-model",
            "reply": "done",
            "skill_candidates": [],
            "tool_matches": [],
            "steps": [{"kind": "final", "title": "Final Result", "content": "done", "metadata": {}}],
        }


def test_console_state_returns_trace_payload() -> None:
    state = ConsoleState()
    state._agent = _FakeAgent()  # type: ignore[assignment]

    result = state.run_chat("hello")

    assert result["reply"] == "done"
    assert result["trace_id"] == "tr_test"
    assert result["steps"][0]["kind"] == "final"
