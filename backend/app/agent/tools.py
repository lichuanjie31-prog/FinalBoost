"""Tool definitions and implementations for the FinalBoost Agent.

Uses LangChain @tool decorators for automatic schema generation.
Each tool is a function that returns a string result.
"""
from __future__ import annotations
import json
import logging
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ── Tool implementations (decorated with @tool) ──────────────────

@tool
def get_study_summary(db_context: str = "") -> str:
    """获取用户的学习情况概览，包括考试列表、判卷次数、薄弱知识点数量等。

    Returns:
        JSON string with study summary data
    """
    # This will be called with actual db context injected by the agent
    # The db_context parameter is a placeholder for dependency injection
    return json.dumps({"message": "请通过 agent 调用此工具"}, ensure_ascii=False)


@tool
def query_weak_points(exam_id: Optional[str] = None, db_context: str = "") -> str:
    """查询用户的薄弱知识点列表。薄弱知识点是指得分率低于80%的知识点。

    Args:
        exam_id: 可选，指定考试ID。不指定则查询所有考试的薄弱知识点。

    Returns:
        JSON string with weak points data
    """
    return json.dumps({"message": "请通过 agent 调用此工具"}, ensure_ascii=False)


@tool
def query_wrong_questions(
    exam_id: Optional[str] = None,
    knowledge_point: Optional[str] = None,
    db_context: str = ""
) -> str:
    """查询用户做错的题目，包括题目信息、得分、错误类型和错误原因。

    Args:
        exam_id: 可选，指定考试ID。不指定则查询所有错题。
        knowledge_point: 可选，按知识点名称筛选错题。

    Returns:
        JSON string with wrong questions data
    """
    return json.dumps({"message": "请通过 agent 调用此工具"}, ensure_ascii=False)


@tool
def explain_question(
    question_description: str,
    course: str,
    knowledge_points: Optional[str] = None,
    error_type: Optional[str] = None,
    error_reason: Optional[str] = None,
    llm_context: str = ""
) -> str:
    """详细讲解一道题目的解题过程，包括知识点回顾、分步骤解题、常见错误分析。

    Args:
        question_description: 题目的描述或内容
        course: 课程名称，如高等数学、线性代数等
        knowledge_points: 涉及的知识点
        error_type: 学生的错误类型：concept_error/method_error/calculation_error/missing_answer
        error_reason: 学生的具体错误原因

    Returns:
        JSON string with detailed explanation
    """
    return json.dumps({"message": "请通过 agent 调用此工具"}, ensure_ascii=False)


@tool
def generate_practice(
    knowledge_point: str,
    course: str,
    difficulty: str = "medium",
    count: int = 3,
    llm_context: str = ""
) -> str:
    """根据知识点和难度生成针对性练习题，附带解题思路和答案。

    Args:
        knowledge_point: 要练习的知识点
        course: 课程名称
        difficulty: 难度等级 (easy/medium/hard)
        count: 题目数量，1-5之间

    Returns:
        JSON string with practice questions
    """
    return json.dumps({"message": "请通过 agent 调用此工具"}, ensure_ascii=False)


@tool
def search_knowledge(query: str, rag_context: str = "") -> str:
    """从知识库中检索与问题相关的文档片段，用于回答用户问题时提供参考资料。

    Args:
        query: 检索查询

    Returns:
        JSON string with relevant document chunks
    """
    return json.dumps({"message": "请通过 agent 调用此工具"}, ensure_ascii=False)


# ── Tool list for binding to LLM ────────────────────────────────

AGENT_TOOLS = [
    get_study_summary,
    query_weak_points,
    query_wrong_questions,
    explain_question,
    generate_practice,
    search_knowledge,
]


# ── Original implementations (for backward compatibility) ─────────

def _get_study_summary_impl(db, user_id: str) -> str:
    """Original implementation for get_study_summary."""
    with db.transaction() as conn:
        exams = conn.execute(
            "SELECT id, course, exam_date, target_score, max_score, stage FROM exams WHERE user_id=? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        gradings = conn.execute(
            "SELECT gj.id, gj.exam_id, gj.status, gj.result_json, e.course FROM grading_jobs gj JOIN exams e ON e.id=gj.exam_id WHERE gj.user_id=? ORDER BY gj.created_at DESC",
            (user_id,),
        ).fetchall()
        diagnoses = conn.execute(
            "SELECT d.data_json, e.course FROM diagnoses d JOIN exams e ON e.id=d.exam_id WHERE d.user_id=? ORDER BY d.created_at DESC",
            (user_id,),
        ).fetchall()
        markings = conn.execute(
            "SELECT mj.id, mj.exam_id, mj.status FROM marking_jobs mj WHERE mj.user_id=? ORDER BY mj.created_at DESC",
            (user_id,),
        ).fetchall()

    if not exams:
        return json.dumps({"message": "用户还没有创建任何考试，请引导用户先创建考试并上传答题图片"}, ensure_ascii=False)

    exam_list = []
    for ex in exams:
        exam_gradings = [g for g in gradings if g["exam_id"] == ex["id"]]
        exam_markings = [m for m in markings if m["exam_id"] == ex["id"]]
        exam_list.append({
            "examId": ex["id"],
            "course": ex["course"],
            "examDate": ex["exam_date"],
            "targetScore": ex["target_score"],
            "maxScore": ex["max_score"],
            "gradingCount": len(exam_gradings),
            "lastGradingStatus": exam_gradings[0]["status"] if exam_gradings else None,
            "markingCount": len(exam_markings),
            "markingSucceededCount": sum(1 for m in exam_markings if m["status"] == "succeeded"),
            "lastMarkingStatus": exam_markings[0]["status"] if exam_markings else None,
        })

    summary = {
        "totalExams": len(exams),
        "totalGradings": len(gradings),
        "totalDiagnoses": len(diagnoses),
        "totalMarkings": len(markings),
        "exams": exam_list,
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


def _query_weak_points_impl(db, user_id: str, exam_id: str | None = None) -> str:
    """Original implementation for query_weak_points."""
    with db.transaction() as conn:
        if exam_id:
            rows = conn.execute(
                "SELECT d.data_json, e.course FROM diagnoses d JOIN exams e ON e.id=d.exam_id WHERE d.user_id=? AND d.exam_id=? ORDER BY d.created_at DESC",
                (user_id, exam_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT d.data_json, e.course FROM diagnoses d JOIN exams e ON e.id=d.exam_id WHERE d.user_id=? ORDER BY d.created_at DESC",
                (user_id,),
            ).fetchall()

    if not rows:
        return json.dumps({"message": "暂无诊断数据。请先上传答题图片并完成判卷。", "weakPoints": []}, ensure_ascii=False)

    weak_points = []
    seen = set()
    for row in rows:
        data = json.loads(row["data_json"])
        for wp in data.get("weakPoints", []):
            key = wp.get("name", "")
            if key and key not in seen:
                seen.add(key)
                weak_points.append({
                    "name": key,
                    "knowledgePointId": wp.get("knowledgePointId"),
                    "course": row["course"],
                })

    return json.dumps({
        "weakPoints": weak_points,
        "total": len(weak_points),
        "message": f"找到 {len(weak_points)} 个薄弱知识点" if weak_points else "暂未发现薄弱知识点",
    }, ensure_ascii=False)


# ── Cloud marking (marking_jobs) query helpers ──────────────────
# A marking result says what the student wrote and whether it was right, but it
# carries no score basis: the result has totalScore/maxScore of None and every
# answer's score is None. Nothing below may turn that into a number.

MAX_MARKING_QUESTIONS = 60

VERDICT_LABEL = {True: "正确", False: "错误"}


def marking_verdict(value) -> bool | None:
    """Tri-state judgement — only an explicit bool is a verdict."""
    return value if isinstance(value, bool) else None


def verdict_label(value) -> str:
    """Render a judgement, keeping an undetermined one explicitly unknown."""
    return VERDICT_LABEL.get(marking_verdict(value), "未判定")


def _marking_job_rows(db, user_id: str, exam_id: str | None = None,
                      marking_job_ids: list[str] | None = None):
    """Load the caller's own finished marking jobs, lowest page first.

    Jobs that have not finished, or that belong to another user, are skipped
    rather than reported as a result.
    """
    sql = ("SELECT mj.id, mj.exam_id, mj.page_index, mj.result_json, e.course "
           "FROM marking_jobs mj JOIN exams e ON e.id = mj.exam_id "
           "WHERE mj.user_id=? AND mj.status='succeeded' AND mj.result_json IS NOT NULL")
    params: list = [user_id]
    if marking_job_ids:
        sql += " AND mj.id IN (" + ",".join("?" * len(marking_job_ids)) + ")"
        params.extend(marking_job_ids)
    if exam_id:
        sql += " AND mj.exam_id=?"
        params.append(exam_id)
    sql += " ORDER BY mj.page_index, mj.created_at"
    with db.transaction() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def _collect_marking_questions(result, limit: int = MAX_MARKING_QUESTIONS) -> list[dict]:
    """Flatten nested marking questions depth-first, capped at ``limit``."""
    collected: list[dict] = []

    def walk(items, depth: int = 0):
        if depth > 16:
            return
        for item in items or []:
            if len(collected) >= limit or not isinstance(item, dict):
                return
            collected.append(item)
            walk(item.get("children"), depth + 1)

    if isinstance(result, dict):
        walk(result.get("questions"))
    return collected


def _marking_question_entries(db, user_id: str, exam_id: str | None = None,
                              marking_job_ids: list[str] | None = None,
                              limit: int = MAX_MARKING_QUESTIONS) -> list[dict]:
    """One entry per (question, answer) pair across the caller's marking jobs.

    Must not be called while holding a ``db.transaction()``.
    """
    entries: list[dict] = []
    for row in _marking_job_rows(db, user_id, exam_id, marking_job_ids):
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError):
            logger.warning("Marking job %s has unreadable result_json", row["id"])
            continue

        page = row["page_index"] + 1
        for item in _collect_marking_questions(result, limit - len(entries)):
            answers = [a for a in (item.get("answers") or []) if isinstance(a, dict)]
            stem = item.get("text") or ""
            # A child question repeats the stem of its parent, so keep the
            # question's own right answer only when it has one of its own.
            question_right = item.get("rightAnswer") or ""
            if not answers:
                # A stem with no detected answer is still worth passing on.
                entries.append({
                    "questionId": f"第{page}页-{item.get('questionId')}",
                    "questionText": stem, "studentAnswer": "", "rightAnswer": question_right,
                    "correct": None, "verdict": verdict_label(None), "analysis": "",
                    "knowledgePoints": [], "errorReason": "", "confidence": None,
                    "pageIndex": row["page_index"], "markingJobId": row["id"],
                    "course": row["course"],
                })
                continue
            for answer in answers:
                entries.append({
                    "questionId": f"第{page}页-{item.get('questionId')}",
                    "questionText": stem,
                    "studentAnswer": answer.get("handwriting") or "",
                    "rightAnswer": answer.get("rightAnswer") or question_right,
                    "correct": marking_verdict(answer.get("correct")),
                    "verdict": verdict_label(answer.get("correct")),
                    "analysis": answer.get("analysis") or "",
                    "knowledgePoints": [kp for kp in (answer.get("knowledgePoints") or []) if kp],
                    "errorReason": answer.get("errorReason") or "",
                    "confidence": answer.get("confidence"),
                    "pageIndex": row["page_index"], "markingJobId": row["id"],
                    "course": row["course"],
                })
            if len(entries) >= limit:
                break
    return entries[:limit]


def _query_marking_questions_impl(db, user_id: str, exam_id: str | None = None,
                                  marking_job_ids: list[str] | None = None,
                                  only_wrong: bool = False) -> str:
    """Question-level detail from the cloud marking results."""
    entries = _marking_question_entries(db, user_id, exam_id, marking_job_ids)
    if only_wrong:
        entries = [e for e in entries if e["correct"] is False]
    undetermined = sum(1 for e in entries if e["correct"] is None)

    return json.dumps({
        "questions": entries[:40],
        "total": len(entries),
        "undetermined": undetermined,
        # Marking provides no score basis; an unknown total stays unknown.
        "scoreAvailable": False,
        "message": (f"共 {len(entries)} 题，其中 {undetermined} 题未判定正误"
                    if entries else "暂无批改结果，请先上传试卷并完成批改"),
    }, ensure_ascii=False)


def _query_wrong_questions_impl(
    db, user_id: str, exam_id: str | None = None, knowledge_point: str | None = None,
    marking_job_ids: list[str] | None = None,
) -> str:
    """Original implementation for query_wrong_questions.

    Covers both grading sources: the legacy ``grading_jobs`` results and the
    cloud ``marking_jobs`` results. An answer whose judgement is undetermined is
    never reported as wrong.
    """
    with db.transaction() as conn:
        if exam_id:
            rows = conn.execute(
                "SELECT gj.result_json, e.course FROM grading_jobs gj JOIN exams e ON e.id=gj.exam_id WHERE gj.user_id=? AND gj.exam_id=? AND gj.status='succeeded' ORDER BY gj.created_at DESC",
                (user_id, exam_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT gj.result_json, e.course FROM grading_jobs gj JOIN exams e ON e.id=gj.exam_id WHERE gj.user_id=? AND gj.status='succeeded' ORDER BY gj.created_at DESC",
                (user_id,),
            ).fetchall()

    wrong_questions = []
    for row in rows:
        result = json.loads(row["result_json"])
        for q in result.get("questions", []):
            if q.get("correct") is False:
                kp_names = q.get("knowledgePoints", [])
                if knowledge_point and not any(knowledge_point in kp for kp in kp_names):
                    continue
                wrong_questions.append({
                    "questionId": q.get("questionId"),
                    "score": q.get("score"),
                    "maxScore": q.get("maxScore"),
                    "knowledgePoints": kp_names,
                    "errorType": q.get("errorType"),
                    "errorReason": q.get("errorReason"),
                    "course": row["course"],
                    "source": "grading",
                })

    for entry in _marking_question_entries(db, user_id, exam_id, marking_job_ids):
        if entry["correct"] is not False:
            continue
        if knowledge_point and not any(knowledge_point in kp for kp in entry["knowledgePoints"]):
            continue
        wrong_questions.append({
            "questionId": entry["questionId"],
            "questionText": entry["questionText"],
            "studentAnswer": entry["studentAnswer"],
            "rightAnswer": entry["rightAnswer"],
            "analysis": entry["analysis"],
            "score": None,
            "maxScore": None,
            "knowledgePoints": entry["knowledgePoints"],
            "errorType": None,
            "errorReason": entry["errorReason"],
            "course": entry["course"],
            "source": "marking",
            "pageIndex": entry["pageIndex"],
            "markingJobId": entry["markingJobId"],
        })

    return json.dumps({
        "wrongQuestions": wrong_questions[:20],
        "total": len(wrong_questions),
        # Marking results carry no score basis, so no score is ever invented here.
        "scoreAvailable": False,
        "message": f"找到 {len(wrong_questions)} 道错题" if wrong_questions else "暂无错题记录",
    }, ensure_ascii=False)


def _explain_question_impl(
    llm_client,
    question_description: str,
    course: str,
    knowledge_points: str = "",
    error_type: str = "",
    error_reason: str = "",
) -> str:
    """Original implementation for explain_question."""
    if llm_client is None:
        mock_explanation = (
            f"**题目**：{question_description}\n\n"
            f"**知识点回顾**：本题考查 {knowledge_points or course + ' 核心概念'}。\n\n"
            "**解题步骤**：\n"
            "1. 首先分析题目，明确考查的知识点和题型\n"
            "2. 回顾相关公式和定理\n"
            "3. 按步骤进行计算或推导\n"
            "4. 检验答案的合理性\n\n"
            "**常见错误**：概念混淆、计算粗心、步骤遗漏。\n\n"
            "**提示**：配置 LLM API Key 后可获得更详细的讲解。"
        )
        return json.dumps({"explanation": mock_explanation}, ensure_ascii=False)

    prompt = f"""请详细讲解以下题目的解题过程：

课程：{course}
题目：{question_description}
{"涉及知识点：" + knowledge_points if knowledge_points else ""}
{"学生错误类型：" + error_type if error_type else ""}
{"学生错误原因：" + error_reason if error_reason else ""}

请按以下结构讲解：
1. **知识点回顾** — 这道题涉及的核心概念
2. **解题步骤** — 分步骤详细写出解题过程（使用 LaTeX 公式）
3. **常见错误** — 学生容易在哪里犯错
4. **关键提醒** — 做这类题的注意事项"""

    response = llm_client.invoke(prompt)
    return json.dumps({"explanation": response.content}, ensure_ascii=False)


def _generate_practice_impl(
    llm_client,
    knowledge_point: str,
    course: str,
    difficulty: str = "medium",
    count: int = 3,
) -> str:
    """Original implementation for generate_practice."""
    count = max(1, min(5, count))

    if llm_client is None:
        mock_practice = (
            f"**题目 1**（{course} · {knowledge_point}）\n"
            f"求不定积分 ∫(2x + 1)dx\n\n"
            f"**解题思路**：利用不定积分的基本公式，逐项积分。\n\n"
            f"**参考答案**：x² + x + C\n\n"
            f"---\n\n"
            f"**题目 2**（{course} · {knowledge_point}）\n"
            f"求定积分 ∫₀² (3x² - 2x)dx\n\n"
            f"**解题思路**：先求不定积分，再代入上下限。\n\n"
            f"**参考答案**：[x³ - x²]₀² = 8 - 4 = 4\n\n"
            f"（以上为 mock 示例，配置 LLM API Key 后可生成更贴合的题目）"
        )
        return json.dumps({
            "practice": mock_practice,
            "knowledgePoint": knowledge_point,
            "course": course,
            "difficulty": difficulty,
            "count": count,
        }, ensure_ascii=False)

    difficulty_map = {"easy": "基础", "medium": "中等", "hard": "困难"}
    diff_cn = difficulty_map.get(difficulty, "中等")

    prompt = f"""请为以下知识点生成 {count} 道练习题：

课程：{course}
知识点：{knowledge_point}
难度：{diff_cn}

对每道题，请按以下格式输出：

**题目 N**
[题目内容，使用 LaTeX 公式]

**解题思路**
[简要说明思路]

**参考答案**
[详细解答过程]

请确保题目难度适当，覆盖该知识点的不同考查角度。"""

    response = llm_client.invoke(prompt)
    return json.dumps({
        "practice": response.content,
        "knowledgePoint": knowledge_point,
        "course": course,
        "difficulty": difficulty,
        "count": count,
    }, ensure_ascii=False)


# ── Execute tool with database context ──────────────────────────

def execute_tool_with_context(
    tool_name: str,
    arguments: dict,
    db,
    user_id: str,
    llm_client=None,
    rag_service=None,
) -> str:
    """Execute a tool with full context (db, user_id, llm).

    This bridges the LangChain tool interface with the original implementations.
    """
    try:
        if tool_name == "get_study_summary":
            return _get_study_summary_impl(db, user_id)
        elif tool_name == "query_weak_points":
            return _query_weak_points_impl(db, user_id, **arguments)
        elif tool_name == "query_wrong_questions":
            return _query_wrong_questions_impl(db, user_id, **arguments)
        elif tool_name == "explain_question":
            return _explain_question_impl(llm_client, **arguments)
        elif tool_name == "generate_practice":
            return _generate_practice_impl(llm_client, **arguments)
        elif tool_name == "search_knowledge":
            if rag_service:
                query = arguments.get("query", "")
                results = rag_service.search(query)
                return json.dumps({"results": results}, ensure_ascii=False)
            return json.dumps({"message": "RAG 服务未启用"}, ensure_ascii=False)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception:
        logger.exception("Tool %s failed", tool_name)
        return json.dumps({"error": f"工具 {tool_name} 执行失败，请稍后重试"}, ensure_ascii=False)
