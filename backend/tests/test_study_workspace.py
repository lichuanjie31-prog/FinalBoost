import io
import json
import threading
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app
from app.grading import LlmGrader, MockGrader
from test_auth import register, bearer, HEADERS
from test_business import setup_exam, post, wait_job, exam_body


def test_mock_mode_never_uses_chat_key_for_grading(tmp_path):
    with TestClient(create_app(data_dir=tmp_path, grading_mode="mock", llm_api_key="test-key", rag_enabled=False)) as c:
        assert isinstance(c.app.state.worker.provider, MockGrader)
        data = c.get("/api/v1/health").json()["data"]
        assert data["gradingMode"] == "mock"
        assert data["chatMode"] == "llm"


def test_real_grading_does_not_block_database_and_preserves_source(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def grade(self, course, maximum, paths):
        assert course == "数据结构" and len(paths) == 1 and paths[0].is_file()
        started.set()
        assert release.wait(5)
        return MockGrader().result()
    monkeypatch.setattr(LlmGrader, "grade", grade)
    with TestClient(create_app(data_dir=tmp_path, grading_mode="llm", grading_api_key="vision-test", llm_api_key="", job_seconds=.01, rag_enabled=False)) as c:
        auth, exam, file = setup_exam(c)
        gid = post(c, "/grading", {"examId": exam["examId"], "fileIds": [file["fileId"]]}, auth).json()["data"]["gradingId"]
        try:
            assert started.wait(3)
            # This read uses BEGIN IMMEDIATE too; it must succeed during the external call.
            assert c.get("/api/v1/exams", headers=auth).status_code == 200
        finally:
            release.set()
        result = wait_job(c, auth, gid)
        assert result["status"] == "succeeded"
        assert result["source"] == "provider"
        assert post(c, f'/exams/{exam["examId"]}/diagnosis', {"gradingId": gid}, auth).json()["data"]["source"] == "provider"


def test_grading_uses_image_bytes_and_single_v1(tmp_path, monkeypatch):
    path = tmp_path / "extensionless-upload"
    output = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, "JPEG")
    path.write_bytes(output.getvalue())
    calls = []
    def respond(self, url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": json.dumps(MockGrader().result())}}]
        })
    monkeypatch.setattr(httpx.Client, "post", respond)
    grader = LlmGrader()
    grader.configure("test", "vision-model", "https://example.com/v1", 10)
    assert grader.grade("数据结构", 100, [path])["totalScore"] == 63
    assert calls[0][0] == "https://example.com/v1/chat/completions"
    assert calls[0][1]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_result_validation_and_missing_knowledge_points():
    grader = LlmGrader()
    fixture = MockGrader().result()
    fixture["questions"][0]["knowledgePoints"] = []
    fixture["questions"][0]["knowledgePointIds"] = []
    assert grader._parse_response(json.dumps(fixture), 100)["questions"][0]["knowledgePoints"]
    fixture["questions"][0]["score"] = 500
    with pytest.raises(ValueError):
        grader._parse_response(json.dumps(fixture), 100)


def test_chat_receives_exam_context_and_rejects_foreign_grading(tmp_path, monkeypatch):
    from app.agent import graph, router
    seen = {}
    monkeypatch.setattr(router, "_get_llm", lambda request: object())
    def run_agent(**kwargs):
        seen.update(kwargs)
        return {"content": "请先复习图论。", "tool_calls": [], "tool_calls_json": None}
    monkeypatch.setattr(graph, "run_agent", run_agent)
    with TestClient(create_app(data_dir=tmp_path, grading_mode="mock", llm_api_key="", job_seconds=.01, rag_enabled=False)) as c:
        auth, exam, file = setup_exam(c)
        gid = post(c, "/grading", {"examId": exam["examId"], "fileIds": [file["fileId"]]}, auth).json()["data"]["gradingId"]
        wait_job(c, auth, gid)
        body = {"message": "分析试卷", "examId": exam["examId"], "gradingId": gid}
        result = c.post("/api/v1/agent/chat", json=body, headers={**HEADERS, **auth})
        assert result.status_code == 200
        assert seen["exam_id"] == exam["examId"] and seen["grading_id"] == gid
        other = post(c, "/exams", exam_body(course="英语"), auth).json()["data"]
        assert c.post("/api/v1/agent/chat", json={**body, "examId": other["examId"]}, headers={**HEADERS, **auth}).status_code == 400
        foreign = bearer(register(c, "student_two"))
        assert c.post("/api/v1/agent/chat", json=body, headers={**HEADERS, **foreign}).status_code == 403


def test_tool_trace_does_not_become_unanswered_calls_on_next_turn(tmp_path):
    from app.agent.memory import MemoryManager
    from langchain_core.messages import AIMessage
    with TestClient(create_app(data_dir=tmp_path, grading_mode="mock", llm_api_key="", rag_enabled=False)) as c:
        auth = bearer(register(c))
        result = c.post("/api/v1/agent/chat", json={"message": "你好"}, headers={**HEADERS, **auth}).json()["data"]
        memory = MemoryManager(c.app.state.db)
        memory.save_message(result["sessionId"], "assistant", "先复习图论", tool_calls=[
            {"id": "trace1", "type": "function", "function": {"name": "query_weak_points", "arguments": "{}"}}
        ])
        history = memory.get_recent_messages(result["sessionId"])
        assert any(m.content == "先复习图论" for m in history)
        assert all(not m.tool_calls for m in history if isinstance(m, AIMessage))


def test_graph_produces_final_answer_at_tool_budget():
    from app.agent.graph import create_agent_graph
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.tools import tool
    @tool
    def lookup() -> str:
        """Return a study fact."""
        return "图论得分偏低"
    class Model:
        calls = 0
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            if isinstance(messages[-1], HumanMessage) and "不再调用工具" in messages[-1].content:
                return AIMessage(content="建议先复习图论。")
            self.calls += 1
            return AIMessage(content="", tool_calls=[{"id": str(self.calls), "name": "lookup", "args": {}}])
    result = create_agent_graph(Model(), [lookup]).invoke({
        "messages": [HumanMessage(content="怎么复习")], "user_id": "test", "session_id": "test", "tool_call_count": 0,
    })
    assert result["messages"][-1].content == "建议先复习图论。"
