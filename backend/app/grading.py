import base64
import json
import logging
import re
import threading
import time
import httpx
import math
import io
from PIL import Image
from .schemas import GradingResult

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
                f"{self.base_url if self.base_url.endswith('/v1') else self.base_url + '/v1'}/chat/completions",
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
                with Image.open(io.BytesIO(data)) as img:
                    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[img.format]
                content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            except Exception:
                raise ValueError("无法读取试卷图片，请重新上传")
        return content

    def _parse_response(self, text: str, max_score: float) -> dict:
        """Parse LLM response into structured grading result."""
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError(f"LLM response is not valid JSON: {text[:200]}")
        data = json.loads(match.group())
        if "questions" not in data or "maxScore" not in data:
            raise ValueError("LLM response missing required fields")
        if not data["questions"]:
            raise ValueError("模型未识别出可评分的题目")
        seen_ids = set()
        for i, q in enumerate(data["questions"], 1):
            q["score"] = round(float(q["score"]), 1) if q.get("score") is not None else None
            q["maxScore"] = float(q["maxScore"])
            if not math.isfinite(q["maxScore"]) or q["maxScore"] <= 0:
                raise ValueError("题目满分无效")
            if q["score"] is not None and (not math.isfinite(q["score"]) or not 0 <= q["score"] <= q["maxScore"]):
                raise ValueError("题目得分超出范围")
            q["questionId"] = str(q.get("questionId") or f"q{i}")
            if q["questionId"] in seen_ids:
                raise ValueError("题目编号重复")
            seen_ids.add(q["questionId"])
            q["correct"] = q["score"] == q["maxScore"] if q["score"] is not None else None
            q["knowledgePointIds"] = q.get("knowledgePointIds") or [f"q{i}_kp"]
            q["knowledgePoints"] = q.get("knowledgePoints") or ["待确认知识点"]
            q["errorType"] = None if q.get("errorType") in (None, "null") else q["errorType"]
            q.setdefault("errorReason", None)
        if not math.isclose(sum(q["maxScore"] for q in data["questions"]), max_score, abs_tol=0.1):
            raise ValueError("识别的题目满分与考试满分不一致，请上传完整试卷")
        data["maxScore"] = max_score
        data["totalScore"] = (round(sum(q["score"] for q in data["questions"]), 1)
                              if all(q["score"] is not None for q in data["questions"]) else None)
        return GradingResult.model_validate(data).model_dump()



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
        if settings.grading_mode == "llm" and (settings.grading_api_key or settings.llm_api_key):
            grader = LlmGrader()
            grader.configure(settings.grading_api_key or settings.llm_api_key, settings.grading_model or settings.llm_model, settings.grading_base_url or settings.llm_base_url, settings.llm_timeout)
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
        # Claim and load one task quickly. Network I/O must not hold a database write lock.
        now = time.time()
        with self.database.transaction() as db:
            db.execute(
                "UPDATE grading_jobs SET status='failed',error_json=? WHERE status IN ('queued','running') AND deadline_at<=?",
                (json.dumps({"code": 50401, "message": "判卷超时，请重新提交"}, ensure_ascii=False), now),
            )
            row = db.execute(
                "SELECT * FROM grading_jobs WHERE status IN ('queued','running') ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return 0.5
            if row["status"] == "queued":
                db.execute("UPDATE grading_jobs SET status='running',started_at=? WHERE id=?", (now, row["id"]))
            if now < row["ready_at"] or row["scenario"] == "timeout":
                next_at = row["deadline_at"] if row["scenario"] == "timeout" else min(row["ready_at"], row["deadline_at"])
                return max(0.001, min(0.1, next_at - now))
            row = dict(row)
            exam = db.execute("SELECT course,max_score FROM exams WHERE id=?", (row["exam_id"],)).fetchone()
            files = db.execute(
                "SELECT f.storage_key FROM grading_files gf JOIN files f ON f.id=gf.file_id WHERE gf.grading_id=? ORDER BY gf.page_index",
                (row["id"],),
            ).fetchall()
            paths = [self.database.data_dir / "uploads" / f["storage_key"] for f in files]

        error, result = None, None
        if row["source"] == "mock" and row["scenario"] in ("unreadable", "provider_error"):
            code = 42201 if row["scenario"] == "unreadable" else 50201
            error = {"code": code, "message": "模拟场景：图片无法识别，请更换清晰图片" if code == 42201 else "模拟场景：判卷服务暂时不可用，请稍后重试"}
        else:
            try:
                if row["source"] == "mock":
                    result = MockGrader().result()
                elif isinstance(self.provider, LlmGrader):
                    result = self.provider.grade(exam["course"], exam["max_score"], paths)
                else:
                    raise ValueError("真实批改模型未配置，请检查服务配置后重新提交")
            except ValueError as exc:
                error = {"code": 42201, "message": str(exc)}
            except Exception:
                logging.getLogger(__name__).exception("Grading failed for job %s", row["id"])
                error = {"code": 50201, "message": "批改模型调用失败，请确认模型支持图片并检查服务配置后重试"}
        if time.time() >= row["deadline_at"]:
            error = {"code": 50401, "message": "判卷超时，请重新提交"}
        with self.database.transaction() as db:
            db.execute(
                "UPDATE grading_jobs SET status=?,result_json=?,error_json=? WHERE id=? AND status='running'",
                ("failed" if error else "succeeded", None if error else json.dumps(result, ensure_ascii=False),
                 json.dumps(error, ensure_ascii=False) if error else None, row["id"]),
            )
        return 0.01
