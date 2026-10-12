"""MCP surface for DuMate's Streamable HTTP connector."""
from app.main import create_app
from app.mcp_bridge import create_mcp_server, service_token_matches
from starlette.routing import Mount
import multiprocessing
import time
import pytest

from app import mcp_bridge


def _slow_child(send_conn):
    time.sleep(2)
    send_conn.send((True, None))
    send_conn.close()


def test_mcp_server_exposes_the_workflow_tools():
    server = create_mcp_server()
    tools = server._tool_manager.list_tools()

    assert {tool.name for tool in tools} == {
        "check_answer",
        "normalize_marking_result",
        "analyze_weak_points",
        "generate_practice_pdf",
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
    started = time.monotonic()

    try:
        with pytest.raises(TimeoutError):
            mcp_bridge._wait_for_process(process, send, receive, 0.1)
        assert not process.is_alive()
        assert time.monotonic() - started < 1.5
    finally:
        receive.close()
        send.close()


def test_mcp_endpoint_is_mounted_at_the_connector_path():
    app = create_app()

    assert any(isinstance(route, Mount) and route.path == "/mcp" for route in app.routes)


def test_mcp_service_token_comparison_rejects_wrong_and_empty_values():
    assert service_token_matches("expected-token", "expected-token") is True
    assert service_token_matches("wrong-token", "expected-token") is False
    assert service_token_matches("", "") is False
