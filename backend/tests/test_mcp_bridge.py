"""MCP surface for DuMate's Streamable HTTP connector."""
from app.main import create_app
import app.mcp_bridge as mcp_bridge
from app.mcp_bridge import create_mcp_server, service_token_matches
from starlette.routing import Mount
import multiprocessing
import time
import pytest


def _slow_child(send_conn):
    send_conn.send(("ready", None))
    time.sleep(2)
    send_conn.send(("result", True, None))
    send_conn.close()


def _delayed_start_child(send_conn):
    time.sleep(0.2)
    send_conn.send(("ready", None))
    send_conn.send(("result", True, "finished"))
    send_conn.close()


def _invalid_data_child(send_conn):
    send_conn.send(("ready", None))
    send_conn.send(("result", False, ("ValueError", "private invalid data")))
    send_conn.close()


def test_mcp_server_exposes_the_workflow_tools():
    server = create_mcp_server()
    tools = server._tool_manager.list_tools()
    assert len(tools) == len({tool.name for tool in tools})

    assert {tool.name for tool in tools} == {
        "check_answer",
        "normalize_marking_result",
        "analyze_weak_points",
        "analyze_four_dimension_diagnosis",
        "generate_practice_pdf",
        "generate_variation_questions",
    }


def test_mcp_check_answer_tool_returns_the_symbolic_verdict():
    server = create_mcp_server()
    tool = server._tool_manager.get_tool("check_answer")

    result = tool.fn(
        problem="化简并比较两个分数",
        studentAnswer="1/2",
        referenceAnswer="0.5",
    )

    assert result["verdict"] == "correct"
    assert set(result) == {"verdict", "reason"}


def test_mcp_check_answer_preserves_a_normal_uncertain_verdict():
    tool = create_mcp_server()._tool_manager.get_tool("check_answer")

    result = tool.fn(
        problem="解方程",
        studentAnswer="无解",
        referenceAnswer="x=1",
    )

    assert result["verdict"] == "uncertain"
    assert result["reason"]
    assert "is_error" not in result


def test_mcp_pdf_success_keeps_the_existing_response_shape():
    tool = create_mcp_server()._tool_manager.get_tool("generate_practice_pdf")
    result = tool.fn(sections=[{"knowledgePoint": "代数", "questions": [{"stem": "1+1=?"}]}])

    assert set(result) == {"filename", "mimeType", "base64"}
    assert result["mimeType"] == "application/pdf"
    assert result["base64"]


def test_mcp_pdf_parse_failure_returns_machine_readable_error():
    tool = create_mcp_server()._tool_manager.get_tool("generate_practice_pdf")
    result = tool.fn(sections=[{"questions": [{"stem": 123}]}])

    assert result["is_error"] is True
    assert result["error_code"] == "PARSE_FAILED"
    assert result["fallback_payload"] is None


def test_mcp_pdf_resource_limit_returns_machine_readable_error():
    tool = create_mcp_server()._tool_manager.get_tool("generate_practice_pdf")
    result = tool.fn(sections=[{"questions": [{"stem": "x" * 1_000_001}]}])

    assert result["error_code"] == "RESOURCE_LIMIT"


def test_mcp_weak_point_resource_limit_returns_machine_readable_error():
    tool = create_mcp_server()._tool_manager.get_tool("analyze_weak_points")
    result = tool.fn(questions=[{}] * 501)

    assert result["error_code"] == "RESOURCE_LIMIT"


def test_mcp_pdf_render_failure_returns_markdown_fallback(monkeypatch):
    tool = create_mcp_server()._tool_manager.get_tool("generate_practice_pdf")
    monkeypatch.setattr(mcp_bridge, "_run_isolated", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("render failed")))

    result = tool.fn(
        sections=[{"knowledgePoint": "代数", "questions": [{"stem": "1+1=?", "answer": "2"}]}],
        includeAnswers=True,
    )

    assert result["error_code"] == "SERVICE_DEGRADED"
    assert result["fallback_payload"]["mimeType"] == "text/markdown"
    assert "答案：2" in result["fallback_payload"]["markdown"]


def test_process_timeout_terminates_the_worker():
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_slow_child, args=(send,), daemon=True)
    try:
        with pytest.raises(TimeoutError, match="operation exceeded"):
            mcp_bridge._wait_for_process(process, send, receive, 0.1)
        assert not process.is_alive()
    finally:
        receive.close()
        send.close()


def test_worker_startup_time_does_not_consume_operation_timeout():
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_delayed_start_child, args=(send,), daemon=True)

    try:
        result = mcp_bridge._wait_for_process(
            process, send, receive, timeout=0.1, startup_timeout=30
        )
        assert result == "finished"
    finally:
        receive.close()
        send.close()


def test_mcp_variation_tool_uses_configured_backend_and_returns_three_tiers(monkeypatch):
    import json

    class LocalModel:
        def __init__(self):
            self.calls = 0

        def invoke(self, prompt):
            self.calls += 1
            tier = next(name for name in ("consolidation", "reverse", "extension")
                        if f"tier 固定为 {name}" in prompt)
            stems = {
                "consolidation": "解一元一次方程 x+1=3",
                "reverse": "一元一次方程已知解为 2，求未知常数",
                "extension": "一元一次方程应用，已知 x=2，求另一个量",
            }
            return type("Response", (), {"content": json.dumps({
                "tier": tier,
                "source_knowledge_point": "一元一次方程",
                "difficulty": "easy",
                "stem": stems[tier],
                "options": None,
                "answer": "2",
                "analysis": "最终答案：2",
            }, ensure_ascii=False)})()

    model = LocalModel()
    def run_with_local_model(operation, arguments, timeout):
        assert operation == "generate_variations"
        assert timeout == mcp_bridge.VARIATION_GENERATION_TIMEOUT_SECONDS
        return mcp_bridge._generate_variation_payload(**arguments, model=model)

    monkeypatch.setattr(mcp_bridge, "_run_isolated", run_with_local_model)
    tool = create_mcp_server()._tool_manager.get_tool("generate_variation_questions")

    result = tool.fn(sourceQuestion="解方程 x+1=3", sourceKnowledgePoint="一元一次方程")

    assert model.calls == 3
    assert [item["tier"] for item in result["questions"]] == ["consolidation", "reverse", "extension"]
    assert all(item["validation_status"] == "passed" for item in result["questions"])


@pytest.mark.parametrize("source_question,source_point", [("", "一元一次方程"), ("解方程 x=2", " "), (123, "一元一次方程")])
def test_mcp_variation_tool_rejects_invalid_input(source_question, source_point):
    tool = create_mcp_server()._tool_manager.get_tool("generate_variation_questions")

    result = tool.fn(sourceQuestion=source_question, sourceKnowledgePoint=source_point)

    assert result["is_error"] is True
    assert result["error_code"] == "PARSE_FAILED"


def test_mcp_variation_tool_enforces_input_size_limit():
    tool = create_mcp_server()._tool_manager.get_tool("generate_variation_questions")

    result = tool.fn(sourceQuestion="x" * (mcp_bridge.MAX_VARIATION_INPUT_CHARS + 1),
                     sourceKnowledgePoint="一元一次方程")

    assert result["is_error"] is True
    assert result["error_code"] == "RESOURCE_LIMIT"


def test_mcp_variation_tool_maps_worker_timeout_to_standard_error(monkeypatch):
    calls = []

    def timeout(operation, arguments, seconds):
        calls.append((operation, arguments, seconds))
        raise TimeoutError("worker timed out")

    monkeypatch.setattr(mcp_bridge, "_run_isolated", timeout)
    tool = create_mcp_server()._tool_manager.get_tool("generate_variation_questions")

    result = tool.fn(sourceQuestion="解方程 x+1=3", sourceKnowledgePoint="一元一次方程")

    assert result["is_error"] is True
    assert result["error_code"] == "TIMEOUT"
    assert result["can_retry"] is False
    assert calls[0][0] == "generate_variations"
    assert calls[0][2] == mcp_bridge.VARIATION_GENERATION_TIMEOUT_SECONDS


def test_mcp_variation_tool_maps_worker_failure_to_standard_error(monkeypatch):
    monkeypatch.setattr(mcp_bridge, "_run_isolated", lambda *args: (_ for _ in ()).throw(RuntimeError("worker failed")))
    tool = create_mcp_server()._tool_manager.get_tool("generate_variation_questions")

    result = tool.fn(sourceQuestion="解方程 x+1=3", sourceKnowledgePoint="一元一次方程")

    assert result["is_error"] is True
    assert result["error_code"] == "SERVICE_DEGRADED"
    assert result["can_retry"] is True


def test_mcp_endpoint_is_mounted_at_the_connector_path():
    app = create_app()

    assert any(isinstance(route, Mount) and route.path == "/mcp" for route in app.routes)


def test_mcp_service_token_comparison_rejects_wrong_and_empty_values():
    assert service_token_matches("expected-token", "expected-token") is True
    assert service_token_matches("wrong-token", "expected-token") is False
    assert service_token_matches("", "") is False


@pytest.mark.parametrize("questions", [None, {}, [123], [{"answers": {"correct": False}}]])
def test_mcp_diagnosis_invalid_input_returns_parse_error(questions):
    tool = create_mcp_server()._tool_manager.get_tool("analyze_four_dimension_diagnosis")
    result = tool.fn(questions=questions)
    assert result["error_code"] == "PARSE_FAILED"
    assert result["is_error"] is True


def test_mcp_diagnosis_question_limit_returns_resource_error():
    tool = create_mcp_server()._tool_manager.get_tool("analyze_four_dimension_diagnosis")
    assert tool.fn(questions=[{}] * 501)["error_code"] == "RESOURCE_LIMIT"


@pytest.mark.parametrize("exception,code", [
    (RuntimeError("private traceback and credentials"), "SERVICE_DEGRADED"),
    (TimeoutError("private timeout"), "TIMEOUT"),
])
def test_mcp_diagnosis_hides_internal_errors(monkeypatch, exception, code):
    def fail(_questions):
        raise exception
    monkeypatch.setattr(mcp_bridge, "diagnose_four_dimensions", fail)
    tool = create_mcp_server()._tool_manager.get_tool("analyze_four_dimension_diagnosis")
    result = tool.fn(questions=[])
    assert result["error_code"] == code
    assert result["can_retry"] is True
    assert "private" not in str(result)


def test_mcp_normalized_marking_feeds_diagnosis_contract():
    from app.tool_contracts import DimensionDiagnosis
    server = create_mcp_server()
    marking = server._tool_manager.get_tool("normalize_marking_result").fn(questions=[{
        "question_text": "化简 2x+3x", "student_answer": "6x",
        "correct_answer": "5x", "judgement": "incorrect",
        "error_reason": "代数计算错误", "knowledge_points": ["整式运算"],
    }])
    result = server._tool_manager.get_tool("analyze_four_dimension_diagnosis").fn(
        questions=marking["questions"])
    dimensions = [DimensionDiagnosis.model_validate(item) for item in result["dimensions"]]
    algebra = next(item for item in dimensions if item.dimension == "algebraic_operation")
    assert algebra.evidence_question_ids == ["1"]
    assert algebra.evidence_count == 1
    assert "代数计算错误" in algebra.reason
    assert "score" not in result


def test_mcp_pdf_timeout_keeps_a_usable_markdown_paper(monkeypatch):
    def timeout(*args):
        raise TimeoutError("render stalled")
    monkeypatch.setattr(mcp_bridge, "_run_isolated", timeout)
    result = create_mcp_server()._tool_manager.get_tool("generate_practice_pdf").fn(
        sections=[{"knowledgePoint": "代数", "questions": [{"stem": "1+1=?", "answer": "2"}]}])
    assert result["error_code"] == "TIMEOUT"
    assert result["fallback_payload"]["mimeType"] == "text/markdown"
    assert "1+1=?" in result["fallback_payload"]["markdown"]
    assert "答案：" not in result["fallback_payload"]["markdown"]


@pytest.mark.parametrize("questions", [
    [{"children": [{}] * 500}],
    [{"answers": [{}] * 2001}],
    [{"questionId": "q1", "answers": [{"errorReason": "x" * 1_000_001}]}],
])
def test_mcp_diagnosis_bounds_the_complete_payload(questions):
    result = create_mcp_server()._tool_manager.get_tool("analyze_four_dimension_diagnosis").fn(
        questions=questions)
    assert result["error_code"] == "RESOURCE_LIMIT"


def test_http_mcp_discovers_and_calls_the_integrated_tools(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.tool_contracts import DimensionDiagnosis
    import json

    monkeypatch.setenv("SERVICE_TOKEN", "local-integration-token")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver,testserver:*")
    app = create_app(data_dir=tmp_path, grading_mode="mock", rag_enabled=False)
    headers = {
        "X-Service-Token": "local-integration-token",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        request_id = 0

        def rpc(method, params=None):
            nonlocal request_id
            request_id += 1
            response = client.post("/mcp/", headers=headers, json={
                "jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {},
            })
            assert response.status_code == 200, response.text
            body = response.json()
            assert "error" not in body, body
            return body["result"]

        initialized = rpc("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "1"},
        })
        assert initialized["serverInfo"]["name"] == "FinalBoost"
        headers["MCP-Protocol-Version"] = initialized["protocolVersion"]
        tools = rpc("tools/list")["tools"]
        assert {tool["name"] for tool in tools} == {
            tool.name for tool in app.state.mcp_server._tool_manager.list_tools()}
        assert len(tools) == 6
        by_name = {tool["name"]: tool for tool in tools}
        assert by_name["analyze_four_dimension_diagnosis"]["inputSchema"]["required"] == ["questions"]
        assert by_name["generate_variation_questions"]["inputSchema"]["required"] == [
            "sourceQuestion", "sourceKnowledgePoint"]

        def call(name, arguments):
            result = rpc("tools/call", {"name": name, "arguments": arguments})
            assert result.get("isError") is not True, result
            assert result["content"][0]["type"] == "text"
            return json.loads(result["content"][0]["text"])

        marking = call("normalize_marking_result", {"questions": [{
            "question_text": "化简 2x+3x", "student_answer": "6x", "judgement": "incorrect",
            "error_reason": "代数计算错误", "knowledge_points": ["整式运算"],
        }]})
        diagnosis = call("analyze_four_dimension_diagnosis", {"questions": marking["questions"]})
        for item in diagnosis["dimensions"]:
            DimensionDiagnosis.model_validate(item)
        assert diagnosis["dimensions"][1]["evidence_question_ids"] == ["1"]
        weak = call("analyze_weak_points", {"questions": marking["questions"]})
        assert weak["weakPoints"][0]["questionIds"] == ["1"]
        verdict = call("check_answer", {
            "problem": "比较集合", "studentAnswer": "{1,2}", "referenceAnswer": "{2,1}",
        })
        assert verdict["verdict"] == "correct"
        invalid = call("analyze_four_dimension_diagnosis", {"questions": [{"answers": "bad"}]})
        assert invalid["error_code"] == "PARSE_FAILED"

        def timeout(*args):
            raise TimeoutError("private worker timeout")
        monkeypatch.setattr(mcp_bridge, "_run_isolated", timeout)
        fallback = call("generate_practice_pdf", {"sections": [{"questions": [{"stem": "1+1=?"}]}]})
        assert fallback["error_code"] == "TIMEOUT"
        assert "1+1=?" in fallback["fallback_payload"]["markdown"]
        variation = call("generate_variation_questions", {
            "sourceQuestion": "解方程 x+1=3", "sourceKnowledgePoint": "一元一次方程",
        })
        assert variation["error_code"] == "TIMEOUT"
        assert "private" not in str(variation)

        from test_variation_generation import SequenceModel, payload
        model = SequenceModel([
            payload("consolidation", "解一元一次方程 x+1=3"),
            payload("reverse", "一元一次方程已知解为 2，求未知常数"),
            payload("extension", "一元一次方程应用，已知 x=2，求另一个量"),
        ])

        def generate_locally(operation, arguments, seconds):
            assert operation == "generate_variations"
            return mcp_bridge._generate_variation_payload(**arguments, model=model)

        monkeypatch.setattr(mcp_bridge, "_run_isolated", generate_locally)
        generated = call("generate_variation_questions", {
            "sourceQuestion": "解方程 x+1=3", "sourceKnowledgePoint": "一元一次方程",
        })
        assert [item["tier"] for item in generated["questions"]] == ["consolidation", "reverse", "extension"]
        assert all(item["validation_status"] == "passed" for item in generated["questions"])

        rejected = client.post("/mcp/", headers={"Accept": headers["Accept"]}, json={
            "jsonrpc": "2.0", "id": 99, "method": "tools/list"})
        assert rejected.status_code == 401


def test_isolated_worker_preserves_parse_failure_semantics():
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_invalid_data_child, args=(send,))
    try:
        with pytest.raises(ValueError, match="invalid data"):
            mcp_bridge._wait_for_process(process, send, receive, timeout=15)
    finally:
        send.close()


def test_variation_missing_model_returns_explicit_service_error(monkeypatch):
    monkeypatch.setattr(mcp_bridge, "create_llm_from_settings", lambda _, **kwargs: None)
    result = mcp_bridge._generate_variation_payload("解方程 x+1=3", "一元一次方程")
    assert result["error_code"] == "SERVICE_DEGRADED"
    assert result["is_error"] is True


def test_variation_invalid_generated_questions_are_an_explicit_parse_error():
    from test_variation_generation import SequenceModel
    result = mcp_bridge._generate_variation_payload(
        "解方程 x+1=3", "一元一次方程", model=SequenceModel(["invalid"] * 9))
    assert result["error_code"] == "PARSE_FAILED"
    assert all(question["validation_status"] == "failed"
               for question in result["fallback_payload"]["questions"])


@pytest.mark.parametrize("exception,code", [
    (RuntimeError("private provider failure"), "SERVICE_DEGRADED"),
    (TimeoutError("private provider timeout"), "TIMEOUT"),
])
def test_variation_provider_failure_keeps_its_business_error(exception, code):
    from test_variation_generation import SequenceModel
    result = mcp_bridge._generate_variation_payload(
        "解方程 x+1=3", "一元一次方程", model=SequenceModel([exception] * 9))
    assert result["error_code"] == code
    assert result["can_retry"] is True
    assert "private" not in str(result)


def test_variation_openai_timeout_keeps_the_timeout_error():
    import httpx
    from openai import APITimeoutError
    from test_variation_generation import SequenceModel
    timeout = APITimeoutError(request=httpx.Request("POST", "https://example.test"))
    result = mcp_bridge._generate_variation_payload(
        "解方程 x+1=3", "一元一次方程", model=SequenceModel([timeout] * 9))
    assert result["error_code"] == "TIMEOUT"
    assert "example.test" not in str(result)
