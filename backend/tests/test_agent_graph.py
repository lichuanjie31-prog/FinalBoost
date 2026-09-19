"""Protocol-level tests for the LangGraph agent loop.

A strict stand-in model checks the tool-calling contract on every call it
receives. The OpenAI-compatible APIs reject an assistant message whose
tool_calls are not answered, and they reject a ToolMessage that answers
nothing, so the stand-in fails loudly if the graph ever hands it such a
transcript — which is exactly what a state channel without a message reducer
used to produce.
"""
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from app.agent.graph import (
    MAX_TOOL_ROUNDS, create_agent_graph, validate_message_protocol,
)
from app.agent.memory import MemoryManager
from app.main import create_app
from test_auth import HEADERS, bearer, register


@tool
def lookup() -> str:
    """Return a study fact."""
    return "图论得分偏低"


def tool_call(name: str, call_id: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": args}])


def is_skipped(message: ToolMessage) -> bool:
    """A tool result the agent refused to run because the budget ran out."""
    return '"skipped": true' in (message.content or "")


class StrictModel:
    """Stand-in chat model that enforces the tool-calling protocol."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.seen = []           # every message list handed to the model
        self.bound_tools = []

    def bind_tools(self, tools):
        self.bound_tools = [t.name for t in tools]
        return self

    def record(self, messages):
        messages = list(messages)
        problems = validate_message_protocol(messages)
        assert not problems, f"illegal transcript handed to the model: {problems}"
        self.seen.append(messages)
        return messages

    def invoke(self, messages):
        self.record(messages)
        return self.script.pop(0) if self.script else AIMessage(content="（脚本已用尽）")


class AlwaysCallsTools(StrictModel):
    """Never stops asking for tools — used to drive the budget to exhaustion."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def invoke(self, messages):
        messages = self.record(messages)
        last = messages[-1]
        if isinstance(last, HumanMessage) and "不再调用工具" in (last.content or ""):
            return AIMessage(content="工具预算已用尽，先给出结论。")
        self.calls += 1
        return tool_call("lookup", f"c{self.calls}")


def state_for(messages, **overrides):
    base = {"messages": messages, "user_id": "u1", "session_id": "s1", "tool_call_count": 0}
    return {**base, **overrides}


def test_second_model_call_keeps_system_user_and_tool_call():
    """Regression: without a reducer the tool round wiped the conversation.

    The second model call used to arrive holding only the ToolMessage, with the
    system prompt, the user question and the assistant tool_calls all gone.
    """
    model = StrictModel([tool_call("lookup", "c1"), AIMessage(content="先复习图论。")])
    graph = create_agent_graph(model, [lookup])

    state = graph.invoke(state_for([SystemMessage(content="系统提示"), HumanMessage(content="怎么复习")]))

    assert len(model.seen) == 2
    second = model.seen[1]
    assert [type(m).__name__ for m in second] == [
        "SystemMessage", "HumanMessage", "AIMessage", "ToolMessage",
    ]
    assert second[0].content == "系统提示"
    assert second[1].content == "怎么复习"
    assert second[2].tool_calls[0]["id"] == "c1"
    assert second[3].tool_call_id == "c1"
    assert second[3].content == "图论得分偏低"

    # The whole turn stays on the record, and it is protocol legal as a whole.
    assert validate_message_protocol(state["messages"]) == []
    assert state["messages"][-1].content == "先复习图论。"
    assert "lookup" in model.bound_tools


def test_tool_budget_exhaustion_closes_dangling_tool_calls():
    """At the budget the model's unanswered tool_calls must still be answered."""
    model = AlwaysCallsTools()
    graph = create_agent_graph(model, [lookup])

    state = graph.invoke(state_for([HumanMessage(content="怎么复习")]))

    assert state["tool_call_count"] == MAX_TOOL_ROUNDS
    executed = [m for m in state["messages"] if isinstance(m, ToolMessage) and not is_skipped(m)]
    assert len(executed) == MAX_TOOL_ROUNDS, "the budget must cap real tool executions"

    assert validate_message_protocol(state["messages"]) == []
    final = state["messages"][-1]
    assert isinstance(final, AIMessage) and final.content == "工具预算已用尽，先给出结论。"
    assert not final.tool_calls, "the turn must end on a plain answer"

    # The refused call was answered on the record rather than silently dropped.
    skipped = [m for m in state["messages"] if isinstance(m, ToolMessage) and is_skipped(m)]
    assert [m.tool_call_id for m in skipped] == [f"c{MAX_TOOL_ROUNDS + 1}"]

    # ...and the prompt that produced the answer carried those answers too.
    summarize_prompt = model.seen[-1]
    assert isinstance(summarize_prompt[-2], ToolMessage)
    assert summarize_prompt[-2].tool_call_id == f"c{MAX_TOOL_ROUNDS + 1}"
    assert "不再调用工具" in summarize_prompt[-1].content


@pytest.mark.parametrize("messages", [
    [AIMessage(content="hi")],
    [SystemMessage(content="s"), HumanMessage(content="h")],
])
def test_validate_message_protocol_accepts_legal_transcripts(messages):
    assert validate_message_protocol(messages) == []


def test_validate_message_protocol_catches_the_two_api_errors():
    dangling = [HumanMessage(content="h"), tool_call("lookup", "c1")]
    assert "unanswered" in " ".join(validate_message_protocol(dangling))

    orphan = [HumanMessage(content="h"), ToolMessage(content="r", tool_call_id="c9")]
    assert "does not answer" in " ".join(validate_message_protocol(orphan))


def test_two_consecutive_turns_keep_history_and_do_not_duplicate_it(tmp_path, monkeypatch):
    """Two turns in one session: complete prompts, legal history, no double saves."""
    from app.agent import router

    model = StrictModel([
        tool_call("get_study_summary_context", "t1"),   # turn 1 asks for a tool
        AIMessage(content="你的薄弱点是图论。"),          # turn 1 answer
        AIMessage(content="建议先复习图论。"),            # turn 2 answer
    ])
    monkeypatch.setattr(router, "_get_llm", lambda request: model)

    with TestClient(create_app(data_dir=tmp_path, grading_mode="mock", llm_api_key="", job_seconds=.01, rag_enabled=False)) as c:
        auth = {**HEADERS, **bearer(register(c))}
        first = c.post("/api/v1/agent/chat", json={"message": "我哪里薄弱"}, headers=auth)
        assert first.status_code == 200, first.text
        session_id = first.json()["data"]["sessionId"]

        second = c.post("/api/v1/agent/chat",
                        json={"message": "那我先看什么", "sessionId": session_id}, headers=auth)
        assert second.status_code == 200, second.text

        # Turn 2's prompt carries turn 1 back to the model, and stays legal.
        turn_two = model.seen[-1]
        transcript = "\n".join(str(m.content) for m in turn_two)
        assert "我哪里薄弱" in transcript
        assert "你的薄弱点是图论。" in transcript
        assert "那我先看什么" in transcript
        assert validate_message_protocol(turn_two) == []

        # Each turn is stored exactly once.
        rows = c.get(f"/api/v1/agent/sessions/{session_id}/messages", headers=auth).json()["data"]
        assert len([m for m in rows if m["role"] == "user"]) == 2
        assert len([m for m in rows if m["role"] == "assistant"]) == 2

        # And the stored history never replays an unanswered tool call.
        assert validate_message_protocol(MemoryManager(c.app.state.db).get_recent_messages(session_id)) == []
