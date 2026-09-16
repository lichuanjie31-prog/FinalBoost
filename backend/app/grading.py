import base64
import json
import logging
import re
import threading
import time
import httpx

GRADING_PROMPT = """你是一位专业的考试判卷助手。请根据以下考试信息和答题图片，完成判卷任务。

## 考试信息
- 课程：{course}
- 满分：{max_score} 分
- 上传了 {file_count} 张答题图片

## 判卷要求
1. 识别试卷中的每道题目，评估学生的作答情况
2. 对每道题给出得分、满分、是否正确、涉及的知识点、错误类型和错误原因
3. 汇总总分
4. 如果无法识别图片内容，请在 error 字段说明原因

## 输出格式（严格 JSON）
```json
{{
  "totalScore": 总得分(数字或null),
  "maxScore": {max_score},
  "questions": [
    {{
      "questionId": "q1",
      "score": 得分(数字或null),
      "maxScore": 满分(数字),
      "correct": true或false或null,
      "knowledgePointIds": ["kp1"],
      "knowledgePoints": ["知识点名称"],
      "errorType": "concept_error|method_error|calculation_error|missing_answer|unrecognized|null",
      "errorReason": "错误原因描述或null"
    }}
  ]
}}
```

## 错误类型说明
- concept_error: 概念理解错误
- method_error: 解题方法错误
- calculation_error: 计算错误
- missing_answer: 未作答
- unrecognized: 无法识别作答内容

请直接输出 JSON，不要包含其他文字。"""


class LlmGrader:
    """Real LLM-based grader using DeepSeek API (OpenAI-compatible)."""

    def __init__(self):
        self.api_key = ""
        self.model = "deepseek-chat"
        self.base_url = "https://api.deepseek.com"
        self.timeout = 60.0

    def configure(self, api_key: str, model: str, base_url: str, timeout: float):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def grade(self, course: str, max_score: float, file_paths: list) -> dict:
        """Send images to LLM for grading. Returns structured result."""
        logger = logging.getLogger(__name__)
        messages = [{"role": "user", "content": self._build_message(course, max_score, file_paths)}]

        logger.info("Calling LLM: %s %s model=%s files=%d", self.base_url, "/v1/chat/completions", self.model, len(file_paths))

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages, "temperature": 0.1},
            )
            logger.info("LLM response status: %d", response.status_code)
            if response.status_code != 200:
                logger.error("LLM API error: %s", response.text[:500])
            response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("LLM response length: %d chars", len(content))
        return self._parse_response(content, max_score)

    def _build_message(self, course: str, max_score: float, file_paths: list) -> list:
        """Build multimodal message with text prompt and images."""
        content = [{"type": "text", "text": GRADING_PROMPT.format(
            course=course, max_score=max_score, file_count=len(file_paths)
        )}]
        for path in file_paths:
            try:
                data = path.read_bytes()
                b64 = base64.b64encode(data).decode()
                suffix = path.suffix.lower().lstrip(".")
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(suffix, "image/png")
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            except Exception:
                logging.getLogger(__name__).warning("Failed to read image %s", path)
        return content

    def _parse_response(self, text: str, max_score: float) -> dict:
        """Parse LLM response into structured grading result."""
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError(f"LLM response is not valid JSON: {text[:200]}")
        data = json.loads(match.group())
        if "questions" not in data or "maxScore" not in data:
            raise ValueError("LLM response missing required fields")
        total = data.get("totalScore")
        if total is not None:
            data["totalScore"] = round(float(total), 1)
        data["maxScore"] = float(data["maxScore"])
        for q in data["questions"]:
            q["score"] = round(float(q["score"]), 1) if q.get("score") is not None else None
            q["maxScore"] = float(q["maxScore"])
            q["correct"] = q.get("correct")
            q.setdefault("knowledgePointIds", [])
            q.setdefault("knowledgePoints", [])
            q.setdefault("errorType", None)
            q.setdefault("errorReason", None)
        return data


class MockGrader:
    """Explicit fixed fixture. Never infers scores from uploaded content."""

    def result(self):
        items = [
            ("链表", 20, 20, None, None),
            ("二叉树遍历", 15, 25, "method_error", "遍历顺序错误"),
            ("Dijkstra", 10, 30, "method_error", "松弛操作错误"),
            ("排序", 18, 25, "method_error", "中间步骤遗漏"),
        ]
        questions = [
            {
                "questionId": f"demo_q{i}",
                "score": score,
                "maxScore": maximum,
                "correct": score == maximum,
                "knowledgePointIds": [f"demo_kp{i}"],
                "knowledgePoints": [name],
                "errorType": error,
                "errorReason": reason,
            }
            for i, (name, score, maximum, error, reason) in enumerate(items, 1)
        ]
        return {"totalScore": 63, "maxScore": 100, "questions": questions}


class GradingWorker:
    def __init__(self, database):
        self.database = database
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="grading-worker")
        self.provider = MockGrader()

    def configure_llm(self, settings):
        """Switch to LLM grader if configured."""
        if settings.llm_api_key:
            grader = LlmGrader()
            grader.configure(settings.llm_api_key, settings.llm_model, settings.llm_base_url, settings.llm_timeout)
            self.provider = grader
            logging.getLogger(__name__).info("Using LLM grader: %s", settings.llm_model)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=20)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            delay = 0.5
            try:
                delay = self.tick()
            except Exception:
                logging.getLogger(__name__).exception("Grading worker tick failed")
            self.wake.wait(delay)

    def tick(self):
        now = time.time()
        next_delay = 0.5
        with self.database.transaction() as db:
            rows = db.execute(
                "SELECT * FROM grading_jobs WHERE status IN ('queued','running') ORDER BY created_at LIMIT 100"
            ).fetchall()
            for row in rows:
                error = None
                if now >= row["deadline_at"]:
                    error = {"code": 50401, "message": "判卷超时，请重新提交"}
                else:
                    if row["status"] == "queued":
                        db.execute(
                            "UPDATE grading_jobs SET status='running',started_at=? WHERE id=?",
                            (now, row["id"]),
                        )
                    # Simulate delay for mock; LLM jobs run immediately
                    if now < row["ready_at"] or row["scenario"] == "timeout":
                        next_at = (
                            row["deadline_at"]
                            if row["scenario"] == "timeout"
                            else min(row["ready_at"], row["deadline_at"])
                        )
                        next_delay = min(next_delay, max(0.001, next_at - now))
                        continue
                    if row["scenario"] == "unreadable":
                        error = {"code": 42201, "message": "模拟场景：图片无法识别，请更换清晰图片"}
                    elif row["scenario"] == "provider_error":
                        error = {"code": 50201, "message": "模拟场景：判卷服务暂时不可用，请稍后重试"}

                if error:
                    db.execute(
                        "UPDATE grading_jobs SET status='failed',error_json=?,result_json=NULL WHERE id=?",
                        (json.dumps(error, ensure_ascii=False), row["id"]),
                    )
                else:
                    result = self._execute_grading(db, row)
                    if result is None:
                        error = {"code": 50201, "message": "判卷服务暂时不可用，请稍后重试"}
                        db.execute(
                            "UPDATE grading_jobs SET status='failed',error_json=?,result_json=NULL WHERE id=?",
                            (json.dumps(error, ensure_ascii=False), row["id"]),
                        )
                    else:
                        db.execute(
                            "UPDATE grading_jobs SET status='succeeded',result_json=?,error_json=NULL WHERE id=?",
                            (json.dumps(result, ensure_ascii=False), row["id"]),
                        )
        return next_delay

    def _execute_grading(self, db, row):
        """Execute grading for a single job. Returns result dict or None on failure."""
        # Mock scenario jobs use mock grader
        if row["scenario"] in ("unreadable", "provider_error", "timeout"):
            if isinstance(self.provider, LlmGrader):
                return MockGrader().result()
            return self.provider.result()

        # LLM grader: read files and send to model
        if isinstance(self.provider, LlmGrader):
            try:
                files = db.execute(
                    "SELECT f.storage_key FROM grading_files gf JOIN files f ON f.id=gf.file_id WHERE gf.grading_id=? ORDER BY gf.page_index",
                    (row["id"],),
                ).fetchall()
                file_paths = [
                    self.database.data_dir / "uploads" / f["storage_key"]
                    for f in files
                ]
                # Get exam info for context
                exam = db.execute(
                    "SELECT course, max_score FROM exams WHERE id=?", (row["exam_id"],)
                ).fetchone()
                course = exam["course"] if exam else "未知课程"
                max_score = exam["max_score"] if exam else 100
                return self.provider.grade(course, max_score, file_paths)
            except Exception:
                logging.getLogger(__name__).exception("LLM grading failed for job %s", row["id"])
                return None

        # Mock grader: return fixed result
        return self.provider.result()
