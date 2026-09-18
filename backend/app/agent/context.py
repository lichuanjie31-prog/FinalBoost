"""Context management for the FinalBoost Agent.

Assembles the conversation context from:
- System prompt (with optional study data injection)
- Recent conversation history
- Current user message
"""
from __future__ import annotations
import json
import logging
from .prompts import build_system_message, SUMMARY_TEMPLATE
from .tools import _get_study_summary

MAX_HISTORY_MESSAGES = 20  # last N messages to include


def build_messages(db, user_id: str, session_id: str, user_message: str,
                    exam_id: str | None = None, grading_id: str | None = None) -> list[dict]:
    """Build the full messages array for the LLM call.

    Returns: list of message dicts in OpenAI format.
    """
    # 1. Get study summary for system prompt
    try:
        raw_summary = _get_study_summary(db, user_id)
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
        logging.getLogger(__name__).exception("Failed to build study summary")
        study_ctx = ""

    # 1b. If grading context is provided, inject grading details
    grading_ctx = ""
    if grading_id:
        try:
            grading_ctx = _build_grading_context(db, user_id, exam_id, grading_id)
        except Exception:
            logging.getLogger(__name__).exception("Failed to build grading context")

    # 2. System message
    full_study = study_ctx + ("\n\n" + grading_ctx if grading_ctx else "")
    system_text = build_system_message(full_study)
    messages = [{"role": "system", "content": system_text}]

    # 3. Recent history
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, name FROM agent_messages "
            "WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
            (session_id, MAX_HISTORY_MESSAGES),
        ).fetchall()

    for row in reversed(rows):
        role = row["role"]
        if role == "assistant":
            msg = {"role": "assistant", "content": row["content"] or ""}
            if row["tool_calls"]:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            messages.append(msg)
        elif role == "tool":
            messages.append({
                "role": "tool",
                "content": row["content"] or "",
                "tool_call_id": row["tool_call_id"],
                "name": row["name"],
            })
        elif role == "user":
            messages.append({"role": "user", "content": row["content"] or ""})

    # 4. Current user message
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