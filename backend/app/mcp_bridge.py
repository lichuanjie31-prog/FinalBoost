"""Authenticated Streamable HTTP MCP facade over FinalBoost's existing rules."""
import base64
import hmac
import json
import os
import tempfile

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Headers
from starlette.responses import JSONResponse

from .analysis import collect_weak_points
from .materials import MaterialPdfIn, _normalize_options
from .marking.models import normalize_qwen_result
from .pdf import render_training_pdf
from .marking.symbolic import check_answer as compare_answers


def service_token_matches(supplied: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(supplied.encode(), expected.encode())


class ServiceTokenMiddleware:
    """Require the same service token as the REST API for every MCP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        expected = os.environ.get("SERVICE_TOKEN", "")
        supplied = Headers(scope=scope).get("X-Service-Token", "")
        if not expected:
            response = JSONResponse(
                {"code": 50301, "message": "服务级 Token 未配置", "data": None},
                status_code=503,
            )
        elif not service_token_matches(supplied, expected):
            response = JSONResponse(
                {"code": 40101, "message": "无效的服务级 Token", "data": None},
                status_code=401,
            )
        else:
            await self.app(scope, receive, send)
            return
        await response(scope, receive, send)


def create_mcp_server() -> FastMCP:
    allowed_hosts = [
        item.strip()
        for item in os.getenv(
            "MCP_ALLOWED_HOSTS",
            "dumate.codehive.asia,dumate.codehive.asia:*",
        ).split(",")
        if item.strip()
    ]
    server = FastMCP(
        name="FinalBoost",
        instructions=(
            "FinalBoost 的理科试卷辅助工具。只校验短数学表达式，"
            "并提供现有批改归一化、薄弱点统计和专项 PDF 生成功能。"
        ),
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
    )

    @server.tool()
    def check_answer(problem: str, studentAnswer: str, referenceAnswer: str) -> dict:
        """Compare a student's short final expression with a verified reference."""
        return compare_answers(problem, studentAnswer, referenceAnswer)

    @server.tool()
    def normalize_marking_result(questions: list[dict], subject: str = "") -> dict:
        """Normalize recognized exam answers into FinalBoost's tri-state schema."""
        return normalize_qwen_result({"questions": questions, "subject": subject})

    @server.tool()
    def analyze_weak_points(questions: list[dict], threshold: float = 0.8) -> dict:
        """Aggregate normalized answers by knowledge point and sort by accuracy."""
        if len(questions) > 500:
            raise ValueError("题目数量异常")
        return {
            "threshold": threshold,
            "weakPoints": collect_weak_points(questions, threshold),
        }

    @server.tool()
    def generate_practice_pdf(
        sections: list[dict],
        title: str = "专项练习卷",
        course: str = "",
        meta: str = "",
        includeAnswers: bool = False,
        includeAnalysis: bool = False,
    ) -> dict:
        """Render a practice paper and return its PDF as base64 for DuMate."""
        body = MaterialPdfIn(
            sections=sections,
            title=title,
            course=course,
            meta=meta,
            includeAnswers=includeAnswers,
            includeAnalysis=includeAnalysis,
        )
        total = sum(len(section.questions) for section in body.sections)
        if total == 0:
            raise ValueError("专项卷没有任何题目")

        groups = []
        for section in body.sections:
            items = [
                {
                    "content": question.stem,
                    "options": _normalize_options(question.options),
                    "answer": question.answer,
                    "analysis": question.analysis,
                }
                for question in section.questions
            ]
            groups.append((section.knowledgePoint or body.course or "专项", items))

        filename = f"{body.title or '专项练习卷'}.pdf"
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                path = handle.name
            render_training_pdf(
                path,
                body.title,
                body.meta or f"{body.course} · 共 {total} 题",
                groups,
                include_answers=body.includeAnswers,
                include_analysis=body.includeAnalysis,
            )
            with open(path, "rb") as pdf_file:
                encoded = base64.b64encode(pdf_file.read()).decode("ascii")
            return {"filename": filename, "mimeType": "application/pdf", "base64": encoded}
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    return server


def create_mcp_app(server: FastMCP):
    app = server.streamable_http_app()
    app.add_middleware(ServiceTokenMiddleware)
    return app
