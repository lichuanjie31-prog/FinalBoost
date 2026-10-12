"""MCP surface for DuMate's Streamable HTTP connector."""
from app.main import create_app
import app.mcp_bridge as mcp_bridge
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
    monkeypatch.setattr(mcp_bridge, "create_llm_from_settings", lambda settings: model)
    tool = create_mcp_server()._tool_manager.get_tool("generate_variation_questions")

    result = tool.fn(sourceQuestion="解方程 x+1=3", sourceKnowledgePoint="一元一次方程")

    assert model.calls == 3
    assert [item["tier"] for item in result["questions"]] == ["consolidation", "reverse", "extension"]
    assert all(item["validation_status"] == "passed" for item in result["questions"])


def test_mcp_endpoint_is_mounted_at_the_connector_path():
    app = create_app()

    assert any(isinstance(route, Mount) and route.path == "/mcp" for route in app.routes)


def test_mcp_service_token_comparison_rejects_wrong_and_empty_values():
    assert service_token_matches("expected-token", "expected-token") is True
    assert service_token_matches("wrong-token", "expected-token") is False
    assert service_token_matches("", "") is False
