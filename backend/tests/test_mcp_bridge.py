"""MCP surface for DuMate's Streamable HTTP connector."""
from app.main import create_app
from app.mcp_bridge import create_mcp_server, service_token_matches
from starlette.routing import Mount


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


def test_mcp_endpoint_is_mounted_at_the_connector_path():
    app = create_app()

    assert any(isinstance(route, Mount) and route.path == "/mcp" for route in app.routes)


def test_mcp_service_token_comparison_rejects_wrong_and_empty_values():
    assert service_token_matches("expected-token", "expected-token") is True
    assert service_token_matches("wrong-token", "expected-token") is False
    assert service_token_matches("", "") is False
