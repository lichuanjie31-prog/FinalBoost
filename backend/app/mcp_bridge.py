"""Authenticated Streamable HTTP MCP facade over FinalBoost's existing rules."""
import base64
import hmac
import json
import multiprocessing
import os
import tempfile
import time
from pydantic import ValidationError

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Headers
from starlette.responses import JSONResponse

from .analysis import collect_weak_points
from .materials import MaterialPdfIn, _normalize_options
from .marking.models import normalize_qwen_result
from .pdf import render_training_pdf
from .marking.symbolic import check_answer as compare_answers
from .tool_contracts import MCPToolError
from .config import Settings
from .agent.llm import create_llm_from_settings
from .services.variation_questions import generate_variation_questions as generate_variations

CHECK_ANSWER_TIMEOUT_SECONDS = 15
PDF_RENDER_TIMEOUT_SECONDS = 15
VARIATION_GENERATION_TIMEOUT_SECONDS = 360
ISOLATED_WORKER_START_TIMEOUT_SECONDS = 30
MAX_PDF_QUESTIONS = 500
MAX_PDF_TEXT_CHARS = 1_000_000
MAX_PDF_BYTES = 10_000_000
MAX_VARIATION_INPUT_CHARS = 20_000


def _isolated_tool_worker(send_conn, operation, arguments):
    """Run potentially unbounded CPU work in a process the caller can stop."""
    send_conn.send(("ready", None))
    try:
        if operation == "check_answer":
            result = compare_answers(**arguments)
        elif operation == "render_pdf":
            render_training_pdf(**arguments)
            result = None
        elif operation == "generate_variations":
            result = _generate_variation_payload(**arguments)
        else:
            raise ValueError("unknown isolated operation")
        send_conn.send(("result", True, result))
    except Exception as exc:
        send_conn.send(("result", False, (type(exc).__name__, str(exc))))
    finally:
        send_conn.close()


def _run_isolated(operation, arguments, timeout):
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_isolated_tool_worker,
        args=(send, operation, arguments),
        # SymPy's bounded checker starts its own worker on Windows.
        daemon=False,
    )
    return _wait_for_process(process, send, receive, timeout)


def _wait_for_process(process, send, receive, timeout,
                      startup_timeout=ISOLATED_WORKER_START_TIMEOUT_SECONDS):
    started = False
    try:
        process.start()
        started = True
        send.close()
        startup_deadline = time.monotonic() + startup_timeout
        if not receive.poll(max(0, startup_deadline - time.monotonic())):
            process.terminate()
            process.join()
            raise TimeoutError(f"worker startup exceeded {startup_timeout} seconds")
        state = receive.recv()
        if not isinstance(state, tuple) or len(state) != 2 or state[0] != "ready":
            raise RuntimeError("isolated worker did not send its ready signal")

        deadline = time.monotonic() + timeout
        if not receive.poll(max(0, deadline - time.monotonic())):
            process.terminate()
            process.join()
            raise TimeoutError(f"operation exceeded {timeout} seconds")
        state = receive.recv()
        process.join()
        if not isinstance(state, tuple) or len(state) != 3 or state[0] != "result":
            raise RuntimeError("isolated worker returned an invalid response")
        _, succeeded, result = state
        if not succeeded:
            name, message = result
            raise RuntimeError(f"{name}: {message}")
        return result
    finally:
        receive.close()
        if started and process.is_alive():
            process.terminate()
            process.join()


def _tool_error(code, message, can_retry=False, fallback_payload=None):
    return MCPToolError(
        error_code=code,
        message=message,
        can_retry=can_retry,
        fallback_payload=fallback_payload,
    ).model_dump()


def _markdown_paper(body):
    lines = [f"# {body.title or '专项练习卷'}", "", body.meta or body.course or ""]
    for section in body.sections:
        lines.extend(["", f"## {section.knowledgePoint or body.course or '专项'}", ""])
        for index, question in enumerate(section.questions, 1):
            lines.extend([f"### 第 {index} 题", "", question.stem])
            for option in _normalize_options(question.options):
                lines.append(f"{option['key']}. {option['text']}")
            if body.includeAnswers and question.answer:
                lines.extend(["", f"答案：{question.answer}"])
            if body.includeAnalysis and question.analysis:
                lines.extend(["", f"解析：{question.analysis}"])
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _generate_variation_payload(sourceQuestion, sourceKnowledgePoint, model=None):
    """Return JSON-ready variation results; model injection supports local tests."""
    if model is None:
        model = create_llm_from_settings(Settings())
    result = generate_variations(model, sourceQuestion, sourceKnowledgePoint)
    return {
        "questions": [item.model_dump(mode="json") for item in result["questions"]],
        "warnings": result["warnings"],
    }


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
            "并提供批改归一化、薄弱点统计、专项 PDF 和三梯次变式题生成功能。"
        ),
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts),
    )

    @server.tool()
    def check_answer(problem: str, studentAnswer: str, referenceAnswer: str) -> dict:
        """Compare a student's short final expression with a verified reference."""
        try:
            return _run_isolated(
                "check_answer",
                {"problem": problem, "student_answer": studentAnswer,
                 "reference_answer": referenceAnswer},
                CHECK_ANSWER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return _tool_error("TIMEOUT", "答案校验超过 15 秒", can_retry=True)
        except Exception:
            return _tool_error("SERVICE_DEGRADED", "答案校验服务暂时不可用", can_retry=True)

    @server.tool()
    def generate_variation_questions(sourceQuestion: str, sourceKnowledgePoint: str) -> dict:
        """Generate and quality-check one question for each of three tiers."""
        if not isinstance(sourceQuestion, str) or not isinstance(sourceKnowledgePoint, str):
            return _tool_error("PARSE_FAILED", "原题和原始考点必须为文本", can_retry=False)
        if not sourceQuestion.strip() or not sourceKnowledgePoint.strip():
            return _tool_error("PARSE_FAILED", "原题和原始考点均为必填项", can_retry=False)
        if len(sourceQuestion) + len(sourceKnowledgePoint) > MAX_VARIATION_INPUT_CHARS:
            return _tool_error("RESOURCE_LIMIT", "原题与考点文本总长度超过 20000 字符", can_retry=False)
        try:
            return _run_isolated(
                "generate_variations",
                {"sourceQuestion": sourceQuestion, "sourceKnowledgePoint": sourceKnowledgePoint},
                VARIATION_GENERATION_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return _tool_error("TIMEOUT", "变式题生成超过 360 秒", can_retry=True)
        except (TypeError, ValueError, ValidationError):
            return _tool_error("PARSE_FAILED", "变式题生成数据格式无效", can_retry=False)
        except Exception:
            return _tool_error("SERVICE_DEGRADED", "变式题生成服务暂时不可用", can_retry=True)

    @server.tool()
    def normalize_marking_result(questions: list[dict], subject: str = "") -> dict:
        """Normalize recognized exam answers into FinalBoost's tri-state schema."""
        try:
            return normalize_qwen_result({"questions": questions, "subject": subject})
        except (TypeError, ValueError, ValidationError):
            return _tool_error("PARSE_FAILED", "批改数据格式无效", can_retry=False)
        except Exception:
            return _tool_error("SERVICE_DEGRADED", "批改归一化服务暂时不可用", can_retry=True)

    @server.tool()
    def analyze_weak_points(questions: list[dict], threshold: float = 0.8) -> dict:
        """Aggregate normalized answers by knowledge point and sort by accuracy."""
        if len(questions) > MAX_PDF_QUESTIONS:
            return _tool_error("RESOURCE_LIMIT", "题目数量超过 500 道", can_retry=False)
        try:
            return {
                "threshold": threshold,
                "weakPoints": collect_weak_points(questions, threshold),
            }
        except (TypeError, ValueError):
            return _tool_error("PARSE_FAILED", "薄弱点数据格式无效", can_retry=False)
        except Exception:
            return _tool_error("SERVICE_DEGRADED", "薄弱点分析服务暂时不可用", can_retry=True)

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
        raw_size = len(json.dumps(sections, ensure_ascii=False, default=str))
        if raw_size > MAX_PDF_TEXT_CHARS:
            return _tool_error("RESOURCE_LIMIT", "题卷文本超过 1 MB 限制", can_retry=False)
        try:
            body = MaterialPdfIn(
                sections=sections,
                title=title,
                course=course,
                meta=meta,
                includeAnswers=includeAnswers,
                includeAnalysis=includeAnalysis,
            )
        except (ValidationError, TypeError, ValueError):
            return _tool_error("PARSE_FAILED", "题卷数据格式无效", can_retry=False)
        total = sum(len(section.questions) for section in body.sections)
        if total == 0:
            return _tool_error("PARSE_FAILED", "专项卷没有任何题目", can_retry=False)
        if total > MAX_PDF_QUESTIONS:
            return _tool_error("RESOURCE_LIMIT", "题目数量超过 500 道", can_retry=False)

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
            render_args = {
                "path": path,
                "title": body.title,
                "meta": body.meta or f"{body.course} · 共 {total} 题",
                "groups": groups,
                "include_answers": body.includeAnswers,
                "include_analysis": body.includeAnalysis,
            }
            try:
                _run_isolated("render_pdf", render_args, PDF_RENDER_TIMEOUT_SECONDS)
            except TimeoutError:
                fallback = {
                    "filename": f"{body.title or '专项练习卷'}.md",
                    "mimeType": "text/markdown",
                    "markdown": _markdown_paper(body),
                }
                return _tool_error("TIMEOUT", "PDF 渲染超过 15 秒，已提供 Markdown 题卷", True, fallback)
            except Exception:
                fallback = {
                    "filename": f"{body.title or '专项练习卷'}.md",
                    "mimeType": "text/markdown",
                    "markdown": _markdown_paper(body),
                }
                return _tool_error("SERVICE_DEGRADED", "PDF 渲染失败，已提供 Markdown 题卷", True, fallback)
            with open(path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read(MAX_PDF_BYTES + 1)
            if len(pdf_bytes) > MAX_PDF_BYTES:
                return _tool_error("RESOURCE_LIMIT", "生成的 PDF 超过 10 MB 限制", can_retry=False)
            encoded = base64.b64encode(pdf_bytes).decode("ascii")
            return {"filename": filename, "mimeType": "application/pdf", "base64": encoded}
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    return server


def create_mcp_app(server: FastMCP):
    app = server.streamable_http_app()
    app.add_middleware(ServiceTokenMiddleware)
    return app
