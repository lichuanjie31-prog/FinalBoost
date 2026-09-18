"""Tool definitions and implementations for the FinalBoost Agent.

Each tool is a function that takes a database connection and user_id,
plus optional keyword arguments from the LLM, and returns a string result.
"""
from __future__ import annotations
import json
import logging
import httpx

logger = logging.getLogger(__name__)

# ── Tool schemas for OpenAI-compatible function calling ──────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_study_summary",
            "description": "获取用户的学习情况概览，包括考试列表、判卷次数、薄弱知识点数量等",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_weak_points",
            "description": "查询用户的薄弱知识点列表。薄弱知识点是指得分率低于80%的知识点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_id": {
                        "type": "string",
                        "description": "可选，指定考试ID。不指定则查询所有考试的薄弱知识点。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_wrong_questions",
            "description": "查询用户做错的题目，包括题目信息、得分、错误类型和错误原因",
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_id": {
                        "type": "string",
                        "description": "可选，指定考试ID。不指定则查询所有错题。",
                    },
                    "knowledge_point": {
                        "type": "string",
                        "description": "可选，按知识点名称筛选错题。",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_question",
            "description": "详细讲解一道题目的解题过程，包括知识点回顾、分步骤解题、常见错误分析",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_description": {
                        "type": "string",
                        "description": "题目的描述或内容",
                    },
                    "knowledge_points": {
                        "type": "string",
                        "description": "涉及的知识点",
                    },
                    "error_type": {
                        "type": "string",
                        "description": "学生的错误类型：concept_error/method_error/calculation_error/missing_answer",
                    },
                    "error_reason": {
                        "type": "string",
                        "description": "学生的具体错误原因",
                    },
                    "course": {
                        "type": "string",
                        "description": "课程名称，如高等数学、线性代数等",
                    },
                },
                "required": ["question_description", "course"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_practice",
            "description": "根据知识点和难度生成针对性练习题，附带解题思路和答案",
            "parameters": {
                "type": "object",
                "properties": {
                    "knowledge_point": {
                        "type": "string",
                        "description": "要练习的知识点",
                    },
                    "course": {
                        "type": "string",
                        "description": "课程名称",
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "难度等级",
                    },
                    "count": {
                        "type": "integer",
                        "description": "题目数量，1-5之间",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["knowledge_point", "course"],
            },
        },
    },
]


# ── Tool implementations ────────────────────────────────────────────

def execute_tool(db, user_id: str, llm_client, name: str, arguments: dict) -> str:
    """Dispatch a tool call to the appropriate handler. Returns a string result."""
    handlers = {
        "get_study_summary": lambda: _get_study_summary(db, user_id),
        "query_weak_points": lambda: _query_weak_points(db, user_id, **arguments),
        "query_wrong_questions": lambda: _query_wrong_questions(db, user_id, **arguments),
        "explain_question": lambda: _explain_question(llm_client, **arguments),
        "generate_practice": lambda: _generate_practice(llm_client, **arguments),
    }
    handler = handlers.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    try:
        return handler()
    except Exception:
        logger.exception("Tool %s failed", name)
        return json.dumps({"error": f"工具 {name} 执行失败，请稍后重试"}, ensure_ascii=False)


def _get_study_summary(db, user_id: str) -> str:
    """Aggregate user's learning data into a summary."""
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

    if not exams:
        return json.dumps({"message": "用户还没有创建任何考试，请引导用户先创建考试并上传答题图片"}, ensure_ascii=False)

    exam_list = []
    for ex in exams:
        exam_gradings = [g for g in gradings if g["exam_id"] == ex["id"]]
        exam_diagnoses = [d for d in diagnoses if True]  # simplified
        exam_list.append({
            "examId": ex["id"],
            "course": ex["course"],
            "examDate": ex["exam_date"],
            "targetScore": ex["target_score"],
            "maxScore": ex["max_score"],
            "gradingCount": len(exam_gradings),
            "lastGradingStatus": exam_gradings[0]["status"] if exam_gradings else None,
        })

    summary = {
        "totalExams": len(exams),
        "totalGradings": len(gradings),
        "totalDiagnoses": len(diagnoses),
        "exams": exam_list,
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


def _query_weak_points(db, user_id: str, exam_id: str | None = None) -> str:
    """Query weak knowledge points (score rate < 80%)."""
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


def _query_wrong_questions(
    db, user_id: str, exam_id: str | None = None, knowledge_point: str | None = None
) -> str:
    """Query wrong questions from grading results."""
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
                })

    return json.dumps({
        "wrongQuestions": wrong_questions[:20],  # limit to 20
        "total": len(wrong_questions),
        "message": f"找到 {len(wrong_questions)} 道错题" if wrong_questions else "暂无错题记录",
    }, ensure_ascii=False)


def _explain_question(
    llm_client,
    question_description: str,
    course: str,
    knowledge_points: str = "",
    error_type: str = "",
    error_reason: str = "",
) -> str:
    """Use LLM to explain a question's solution in detail."""
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

    response = llm_client.chat(prompt)
    return json.dumps({"explanation": response}, ensure_ascii=False)


def _generate_practice(
    llm_client,
    knowledge_point: str,
    course: str,
    difficulty: str = "medium",
    count: int = 3,
) -> str:
    """Use LLM to generate practice questions."""
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

    response = llm_client.chat(prompt)
    return json.dumps({
        "practice": response,
        "knowledgePoint": knowledge_point,
        "course": course,
        "difficulty": difficulty,
        "count": count,
    }, ensure_ascii=False)


# ── LLM Client wrapper ──────────────────────────────────────────────

class LLMClient:
    """Thin wrapper around DeepSeek (OpenAI-compatible) API."""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat_completion(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Call the chat completions API. Returns the full response object."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2000,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
        return resp.json()

    def chat(self, user_message: str, system: str | None = None) -> str:
        """Simple single-turn chat (used by tool implementations like explain/generate)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})
        data = self.chat_completion(messages)
        return data["choices"][0]["message"]["content"]