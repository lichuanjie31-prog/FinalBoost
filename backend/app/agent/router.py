"""Agent API routes.

Endpoints:
- POST   /api/v1/agent/chat               — Send a message, get AI response
- GET    /api/v1/agent/sessions             — List user's chat sessions
- GET    /api/v1/agent/sessions/{id}/messages — Get messages in a session
- DELETE /api/v1/agent/sessions/{id}        — Delete a session
- POST   /api/v1/agent/knowledge/upload     — Upload document to knowledge base
- GET    /api/v1/agent/knowledge            — List knowledge documents
- DELETE /api/v1/agent/knowledge/{id}       — Delete knowledge document
"""
from __future__ import annotations
import json
import logging
import time
import uuid
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from ..auth import current_user
from ..business import owned
from ..common import envelope, fail, new_id
from .schemas import ChatRequest, ChatResponse, SessionOut, MessageOut, ToolCallOut
from .memory import MemoryManager
from .llm import create_llm_from_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def _get_llm(request: Request):
    """Get or create an LLM client from app settings. Returns None in mock mode."""
    settings = request.app.state.settings
    return create_llm_from_settings(settings)


def _get_rag_service(request: Request):
    """Get RAG service from app state."""
    return getattr(request.app.state, 'rag_service', None)


def _session_out(row, last_msg: str | None = None) -> dict:
    return {
        "sessionId": row["id"],
        "title": row["title"],
        "course": row["course"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "lastMessage": last_msg,
    }


def _message_out(row) -> dict:
    tool_calls = []
    if row["tool_calls"]:
        try:
            raw = json.loads(row["tool_calls"])
            tool_calls = [
                ToolCallOut(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", tc.get("name", "")),
                    arguments=_parse_args(tc),
                    result=None,
                ).model_dump()
                for tc in raw
            ]
        except (json.JSONDecodeError, KeyError):
            pass

    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "toolCalls": tool_calls,
        "toolCallId": row["tool_call_id"],
        "name": row["name"],
        "createdAt": row["created_at"],
    }


def _parse_args(tc: dict) -> dict:
    fn = tc.get("function", {})
    args = fn.get("arguments", "{}")
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {}
    return args if isinstance(args, dict) else {}


@router.post("/chat")
def agent_chat(body: ChatRequest, request: Request, user=Depends(current_user)):
    """Send a message to the AI Agent and get a response."""
    db = request.app.state.db
    with db.transaction() as conn:
        if body.examId:
            owned(conn, "exams", body.examId, user["id"])
        if body.gradingId:
            job = owned(conn, "grading_jobs", body.gradingId, user["id"])
            if body.examId and job["exam_id"] != body.examId:
                fail(400, "判卷记录不属于当前考试")
            if job["status"] != "succeeded":
                fail(409, "判卷尚未完成，请稍后再分析")
            body.examId = job["exam_id"]
        if body.markingJobIds:
            # Every job must belong to the caller, be finished, and come from the
            # same exam — a batch is the pages of one paper.
            marking_ids = list(dict.fromkeys(body.markingJobIds))
            exam_ids = set()
            for marking_id in marking_ids:
                job = owned(conn, "marking_jobs", marking_id, user["id"])
                if body.examId and job["exam_id"] != body.examId:
                    fail(400, "批改任务不属于当前考试")
                if job["status"] != "succeeded":
                    fail(409, "批改尚未完成，请稍后再分析")
                exam_ids.add(job["exam_id"])
            if len(exam_ids) > 1:
                fail(400, "批改任务必须属于同一场考试")
            body.markingJobIds = marking_ids
            body.examId = exam_ids.pop()
    llm = _get_llm(request)
    rag_service = _get_rag_service(request)
    memory_manager = MemoryManager(db)
    now = time.time()

    # Get or create session
    with db.transaction() as conn:
        if body.sessionId:
            session = conn.execute(
                "SELECT * FROM agent_sessions WHERE id=? AND user_id=?",
                (body.sessionId, user["id"]),
            ).fetchone()
            if not session:
                fail(404, "会话不存在")
            session_id = session["id"]
        else:
            session_id = new_id()
            title = body.message[:30] + ("..." if len(body.message) > 30 else "")
            conn.execute(
                "INSERT INTO agent_sessions(id, user_id, title, course, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (session_id, user["id"], title, body.course, now, now),
            )

    # Mock mode: return a canned response without calling LLM
    logger.info("Agent chat: llm=%s, message=%s, examId=%s, gradingId=%s, markingJobIds=%s",
                llm, body.message[:50], body.examId, body.gradingId, body.markingJobIds)

    if llm is None:
        result = _mock_agent_turn(db, user["id"], body.message, body.examId,
                                  body.gradingId, body.markingJobIds)
    else:
        try:
            # Use LangGraph agent
            from .graph import run_agent
            result = run_agent(
                llm=llm,
                db=db,
                user_id=user["id"],
                session_id=session_id,
                user_message=body.message,
                memory_manager=memory_manager,
                rag_service=rag_service,
                exam_id=body.examId,
                grading_id=body.gradingId,
                marking_job_ids=body.markingJobIds,
            )
        except Exception:
            logger.exception("Agent turn failed for user %s session %s", user["id"], session_id)
            fail(502, "AI 服务暂时不可用，请稍后重试")
            return  # unreachable, keeps type checker happy

    # Persist messages using memory manager
    memory_manager.save_message(session_id, "user", body.message)
    memory_manager.save_message(
        session_id, "assistant", result["content"],
        tool_calls=result.get("tool_calls_json"),
    )
    memory_manager.update_session_timestamp(session_id)

    return envelope({
        "sessionId": session_id,
        "message": result["content"],
        "toolCalls": [
            {
                "id": tc["id"],
                "name": tc["name"],
                "arguments": tc["arguments"],
                "result": tc["result"],
            }
            for tc in result["tool_calls"]
        ],
    })


def _mock_agent_turn(db, user_id: str, message: str, exam_id: str | None = None,
                     grading_id: str | None = None,
                     marking_job_ids: list[str] | None = None) -> dict:
    """Generate a mock agent response for demo/testing without an LLM key."""
    msg_lower = message.lower()
    tool_calls = []

    # Cloud marking batch: report what the marking results actually contain.
    # The reply is canned, but the tool card carries the real stored data.
    if marking_job_ids:
        from .tools import _query_marking_questions_impl
        result_str = _query_marking_questions_impl(db, user_id, exam_id, marking_job_ids)
        try:
            total = json.loads(result_str).get("total", 0)
        except json.JSONDecodeError:
            total = 0
        tc_id = new_id()
        tool_calls.append({
            "id": tc_id, "name": "query_marking_questions",
            "arguments": {"marking_job_ids": marking_job_ids}, "result": result_str,
        })
        reply = (f"**本次批改结果**\n\n我读取了这次上传的批改结果，共 {total} 题，"
                 "点击上方工具卡片可以查看每道题的题干、你的作答、正误判定和解析。\n\n"
                 "本次批改没有提供评分依据，因此不会给出分数。"
                 "你可以继续问我某一道题的讲解或需要复习的知识点。")
        return {"content": reply, "tool_calls": tool_calls, "tool_calls_json": None}

    # If grading context is provided, generate a grading analysis response
    if grading_id:
        from .tools import _query_weak_points_impl
        result_str = _query_weak_points_impl(db, user_id, exam_id)
        tc_id = new_id()
        tool_calls.append({"id": tc_id, "name": "query_weak_points", "arguments": {"exam_id": exam_id or ""}, "result": result_str})
        reply = ("**AI 判卷分析**\n\n"
                 "我查看了你这次的判卷结果和薄弱知识点数据。\n\n"
                 "根据分析：\n"
                 "- 你的部分知识点得分率较低，建议重点关注\n"
                 "- 可以针对薄弱知识点做专项练习\n\n"
                 "点击上方工具卡片查看详细数据。你可以继续问我「讲解错题」或「生成练习题」。")
        return {"content": reply, "tool_calls": tool_calls, "tool_calls_json": None}

    # Decide which mock tool to "call" based on keywords
    if any(k in msg_lower for k in ['薄弱', '不会', '差', '弱', 'weak']):
        from .tools import _query_weak_points_impl
        result_str = _query_weak_points_impl(db, user_id)
        tc_id = new_id()
        tool_calls.append({"id": tc_id, "name": "query_weak_points", "arguments": {}, "result": result_str})
        reply = ("根据你的学习数据，我帮你查询了薄弱知识点。\n\n"
                 "你可以点击上方的工具卡片查看详细数据。\n\n"
                 "建议你针对这些薄弱知识点多做练习，我可以帮你生成专项训练题。")
    elif any(k in msg_lower for k in ['错题', '做错', '错误', 'wrong', 'mistake']):
        from .tools import _query_wrong_questions_impl
        result_str = _query_wrong_questions_impl(db, user_id)
        tc_id = new_id()
        tool_calls.append({"id": tc_id, "name": "query_wrong_questions", "arguments": {}, "result": result_str})
        reply = ("我帮你查询了最近的错题记录。\n\n"
                 "如果你需要我详细讲解某道题的解题过程，可以告诉我题目的内容和课程名称。")
    elif any(k in msg_lower for k in ['分析', '情况', '概览', '总结', 'analyze', 'summary', 'overview']):
        from .tools import _get_study_summary_impl
        result_str = _get_study_summary_impl(db, user_id)
        tc_id = new_id()
        tool_calls.append({"id": tc_id, "name": "get_study_summary", "arguments": {}, "result": result_str})
        reply = ("我帮你查看了学习概览。\n\n"
                 "目前你的备考数据如上方工具卡片所示。如果还没有上传过答题图片，"
                 "建议先去「我的备考」创建考试计划并上传作答，这样我才能更准确地分析你的学习情况。")
    elif any(k in msg_lower for k in ['练习', '题目', '出题', '训练', 'practice', 'exercise', 'generate']):
        from .tools import _generate_practice_impl
        result_str = _generate_practice_impl(None, knowledge_point="定积分", course="高等数学", difficulty="medium", count=2)
        tc_id = new_id()
        tool_calls.append({"id": tc_id, "name": "generate_practice", "arguments": {"knowledge_point": "定积分", "course": "高等数学"}, "result": result_str})
        reply = ("我为你生成了针对性练习题，点击上方工具卡片查看详情。\n\n"
                 "建议先独立完成，再对照参考答案检查。")
    elif any(k in msg_lower for k in ['讲解', '解释', '怎么解', '怎么做', 'explain', 'how to']):
        from .tools import _explain_question_impl
        result_str = _explain_question_impl(None, question_description="求定积分 ∫₀¹ x²dx", course="高等数学")
        tc_id = new_id()
        tool_calls.append({"id": tc_id, "name": "explain_question", "arguments": {"question_description": "求定积分"}, "result": result_str})
        reply = ("我来讲解一下这道题的解题思路。\n\n"
                 "点击上方工具卡片查看详细的分步讲解。")
    else:
        reply = ("你好！我是 FinalBoost AI 学习伙伴。\n\n"
                 "我可以帮你：\n"
                 "- **分析学习情况** — 查看你的备考数据\n"
                 "- **查询薄弱知识点** — 找到需要加强的部分\n"
                 "- **讲解错题** — 详细分析解题过程\n"
                 "- **生成练习题** — 针对性练习\n\n"
                 "试着问我：「帮我分析一下学习情况」或「我有哪些薄弱知识点」？")

    return {"content": reply, "tool_calls": tool_calls, "tool_calls_json": None}


@router.get("/sessions")
def list_sessions(request: Request, user=Depends(current_user)):
    """List user's chat sessions."""
    db = request.app.state.db
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
        sessions = []
        for row in rows:
            last = conn.execute(
                "SELECT content FROM agent_messages WHERE session_id=? AND role='user' ORDER BY created_at DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            sessions.append(_session_out(row, last["content"] if last else None))
    return envelope(sessions)


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, request: Request, user=Depends(current_user)):
    """Get all messages in a session."""
    db = request.app.state.db
    with db.transaction() as conn:
        session = conn.execute(
            "SELECT * FROM agent_sessions WHERE id=? AND user_id=?",
            (session_id, user["id"]),
        ).fetchone()
        if not session:
            fail(404, "会话不存在")
        rows = conn.execute(
            "SELECT * FROM agent_messages WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    return envelope([_message_out(row) for row in rows])


@router.delete("/sessions/{session_id}", status_code=200)
def delete_session(session_id: str, request: Request, user=Depends(current_user)):
    """Delete a chat session and all its messages."""
    db = request.app.state.db
    with db.transaction() as conn:
        session = conn.execute(
            "SELECT * FROM agent_sessions WHERE id=? AND user_id=?",
            (session_id, user["id"]),
        ).fetchone()
        if not session:
            fail(404, "会话不存在")
        conn.execute("DELETE FROM agent_messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM agent_sessions WHERE id=?", (session_id,))
    return envelope({"deleted": True})


# ── Knowledge base management endpoints ──────────────────────────

@router.post("/knowledge/upload")
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
    title: str = None,
    user=Depends(current_user),
):
    """Upload a document to the knowledge base for RAG."""
    rag_service = _get_rag_service(request)
    if not rag_service:
        fail(503, "RAG 服务未启用")

    # Read file content
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    if not text.strip():
        fail(400, "文件内容为空")

    # Generate document ID
    doc_id = new_id()
    doc_title = title or file.filename or "Untitled"

    # Index the document
    try:
        chunk_count = rag_service.add_document(
            user_id=user["id"],
            doc_id=doc_id,
            content=text,
            metadata={"title": doc_title, "filename": file.filename},
        )
    except Exception:
        logger.exception("Failed to index document")
        fail(500, "文档索引失败")

    return envelope({
        "documentId": doc_id,
        "title": doc_title,
        "chunkCount": chunk_count,
    })


@router.get("/knowledge")
def list_knowledge(request: Request, user=Depends(current_user)):
    """List knowledge documents for the current user."""
    rag_service = _get_rag_service(request)
    if not rag_service:
        return envelope([])

    # This is a simplified version - in production you'd want a proper
    # document metadata table in MySQL
    return envelope([])


@router.delete("/knowledge/{doc_id}", status_code=200)
def delete_knowledge(doc_id: str, request: Request, user=Depends(current_user)):
    """Delete a knowledge document."""
    rag_service = _get_rag_service(request)
    if not rag_service:
        fail(503, "RAG 服务未启用")

    try:
        rag_service.delete_document(doc_id)
    except Exception:
        logger.exception("Failed to delete document")
        fail(500, "文档删除失败")

    return envelope({"deleted": True})
