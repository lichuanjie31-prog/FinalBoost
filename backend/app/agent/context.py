"""Context management for the FinalBoost Agent.

Now uses MemoryManager and RagService for context assembly.
This module provides backward-compatible functions that delegate to the new systems.
"""
from __future__ import annotations
import json
import logging
from .prompts import build_system_message, SUMMARY_TEMPLATE
from .memory import MemoryManager

MAX_HISTORY_MESSAGES = 20  # last N messages to include

logger = logging.getLogger(__name__)


def build_messages(db, user_id: str, session_id: str, user_message: str,
                   exam_id: str | None = None, grading_id: str | None = None) -> list[dict]:
    """Build the full messages array for the LLM call.

    This is the legacy interface. For new code, use MemoryManager directly.

    Returns: list of message dicts in OpenAI format.
    """
    memory_manager = MemoryManager(db)

    # 1. Get study summary for system prompt
    try:
        from .tools import _get_study_summary_impl
        raw_summary = _get_study_summary_impl(db, user_id)
        summary_data = json.loads(raw_summary)
        if "message" in summary_data and "totalExams" not in summary_data:
            study_ctx = SUMMARY_TEMPLATE.format(data=summary_data["message"])
        else:
            lines = []
            for ex in summary_data.get("exams", []):
                lines.append(f"- {ex['course']}：目标 {ex['targetScore']}分/{ex['maxScore']}分，"
                             f"考试日期 {ex['examDate']}，已判卷 {ex['gradingCount']} 次")
            if not lines:
                study_ctx = SUMMARY_TEMPLATE.format(data="暂无学习数据。")
            else:
                study_ctx = SUMMARY_TEMPLATE.format(data="\n".join(lines))
    except Exception:
        logger.exception("Failed to build study summary")
        study_ctx = ""

    # 1b. If grading context is provided, inject grading details
    grading_ctx = ""
    if grading_id:
        try:
            grading_ctx = _build_grading_context(db, user_id, exam_id, grading_id)
        except Exception:
            logger.exception("Failed to build grading context")

    # 2. System message
    full_study = study_ctx + ("\n\n" + grading_ctx if grading_ctx else "")
    system_text = build_system_message(full_study)
    messages = [{"role": "system", "content": system_text}]

    # 3. Long-term memories
    memories = memory_manager.get_long_term_memories(user_id, user_message)
    if memories:
        memory_text = "以下是只读的历史事实，仅供参考：\n" + "\n".join(f"- {m}" for m in memories)
        messages.append({"role": "system", "content": memory_text})

    # 4. Recent history
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, name FROM agent_messages "
            "WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
            (session_id, MAX_HISTORY_MESSAGES),
        ).fetchall()

    for row in reversed(rows):
        role = row["role"]
        if role == "assistant":
            msg: dict = {"role": "assistant"}
            tc = json.loads(row["tool_calls"]) if row["tool_calls"] else None
            if tc:
                for t in tc:
                    t.setdefault("type", "function")
                msg["tool_calls"] = tc
                if row["content"]:
                    msg["content"] = row["content"]
            else:
                msg["content"] = row["content"] or ""
            messages.append(msg)
        elif role == "tool":
            tool_msg: dict = {
                "role": "tool",
                "content": row["content"] or "",
                "tool_call_id": row["tool_call_id"],
            }
            if row["name"]:
                tool_msg["name"] = row["name"]
            messages.append(tool_msg)
        elif role == "user":
            messages.append({"role": "user", "content": row["content"] or ""})

    # 5. Current user message
    messages.append({"role": "user", "content": user_message})

    return messages


def _build_grading_context(db, user_id: str, exam_id: str | None, grading_id: str) -> str:
    """Fetch grading result and build context string for the LLM."""
    with db.transaction() as conn:
        grading = conn.execute(
            "SELECT * FROM grading_jobs WHERE id=? AND user_id=?",
            (grading_id, user_id),
        ).fetchone()
        if not grading or not grading["result_json"]:
            return ""

        exam = None
        if exam_id:
            exam = conn.execute(
                "SELECT * FROM exams WHERE id=? AND user_id=?",
                (exam_id, user_id),
            ).fetchone()

    result = json.loads(grading["result_json"])
    lines = ["## 当前判卷结果详情"]

    if exam:
        lines.append(f"- 课程：{exam['course']}")
        lines.append(f"- 目标分数：{exam['target_score']}/{exam['max_score']}")

    total = result.get("totalScore")
    maximum = result.get("maxScore")
    if total is not None and maximum:
        lines.append(f"- 总分：{total}/{maximum}（得分率 {round(total/maximum*100, 1)}%）")

    questions = result.get("questions", [])
    if questions:
        lines.append(f"\n### 逐题得分（共 {len(questions)} 题）")
        for q in questions:
            status = "✓" if q.get("correct") else "✗"
            kp = ", ".join(q.get("knowledgePoints", []))
            score_str = f"{q.get('score', '?')}/{q.get('maxScore', '?')}"
            line = f"- {status} {score_str}"
            if kp:
                line += f"  知识点：{kp}"
            if q.get("errorType") and q["errorType"] != "null":
                err_map = {
                    "concept_error": "概念错误",
                    "method_error": "方法错误",
                    "calculation_error": "计算错误",
                    "missing_answer": "未作答",
                    "unrecognized": "无法识别",
                }
                line += f"  错误类型：{err_map.get(q['errorType'], q['errorType'])}"
            if q.get("errorReason"):
                line += f"  原因：{q['errorReason']}"
            lines.append(line)

    lines.append("\n请基于以上判卷数据，为用户提供有针对性的分析和建议。")
    return "\n".join(lines)
