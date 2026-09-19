"""Qwen VL exam-marking provider (DashScope, OpenAI-compatible mode).

Verified against the official Model Studio documentation and the `openai` SDK
type definitions rather than recalled:

* Endpoint:   ``{base}/chat/completions`` where base is
  ``https://dashscope.aliyuncs.com/compatible-mode/v1`` — the same base URL this
  project already uses for Alibaba embeddings.
* Model:      ``qwen3-vl-plus`` (listed as supporting 结构化输出 / structured output).
* Image part: ``{"type": "image_url", "image_url": {"url": "data:image/png;base64,…"}}``
* Structured output:
  ``{"type": "json_schema", "json_schema": {"name", "description", "schema", "strict"}}``
  — `name` is required; `strict` is recommended.

Unlike Tencent, this is a synchronous multimodal call: there is no remote job to
poll, so the provider returns a finished outcome directly.
"""
import base64
import json
import time

import httpx

from .base import ProviderError, ProviderOutcome, prepare_image
from .models import normalize_qwen_result

SYSTEM_PROMPT = """你是一名大学课程试卷批改教师，负责批改高等数学、概率论、离散数学、数据结构、大学物理等课程的试卷。

你的任务是分析图片中的试卷，并产出一份结构化的批改结果。

必须遵守以下要求：

1. 自动识别题目编号。
2. 识别题干内容。
3. 识别学生实际写在卷面上的作答内容。
4. 独立求解每一道题，得到你认为正确的答案。
5. 将学生答案与你的答案比较，判定为以下三者之一：
   - correct：学生答案正确
   - incorrect：学生答案明确错误
   - undetermined：无法可靠判断
6. 给出正确答案。
7. 给出简洁解析（说明解题思路与关键步骤）。
8. 给出错误原因（仅在 incorrect 时填写，否则留空字符串）。
9. 提取 1~5 个知识点。
10. 如果无法可靠识别学生的作答内容，必须返回 undetermined，禁止猜测。
11. 如果图片模糊、遮挡或裁切导致内容无法辨认，不得把无法识别的答案判为错误。
12. 不要虚构百分制分数。
13. 没有评分标准时，不要计算总分。
14. 保留大题与小题的层级结构：小题放在所属大题的 children 中，最深层 children 为空数组。
15. 只输出 JSON，不要输出 Markdown 代码块，不要输出任何解释性文字。

特别重要：
“判断学生写了什么”与“你自己解题得到什么”是两件必须分开的事情。
不能因为你算出了正确答案，就假设学生也是这么写的。
必须严格按照图片上学生实际书写的内容来判定，识别不清就返回 undetermined。"""

USER_PROMPT = """请批改这张试卷图片。

注意：
- 逐题给出结果，不要遗漏题目。
- student_answer 必须是学生在卷面上实际书写的内容原文（可做必要的公式转写），
  不要填入你自己求解得到的答案。
- 如果某题学生的作答无法辨认，judgement 必须是 undetermined，并在 analysis 中说明原因。
- 严格按给定的 JSON Schema 输出。"""

# Judgements map onto the unified DTO's tri-state `correct` field. Anything that is
# not explicitly correct/incorrect becomes null (= 未判定), never False.
JUDGEMENTS = ("correct", "incorrect", "undetermined")

MAX_QUESTION_DEPTH = 2  # 大题 + 小题; a self-referencing $ref is not worth the risk

_FIELDS = {
    "question_id": {"type": "string", "description": "题目唯一标识，如 1 或 1.2"},
    "question_number": {"type": "string", "description": "卷面上印的题号，如 一、1、(2)"},
    "question_text": {"type": "string", "description": "题干原文"},
    "question_type": {"type": "string", "description": "题型，如 计算题、证明题、选择题"},
    "student_answer": {"type": "string", "description": "学生在卷面上实际书写的内容原文"},
    "judgement": {"type": "string", "enum": list(JUDGEMENTS)},
    "correct_answer": {"type": "string", "description": "正确答案"},
    "analysis": {"type": "string", "description": "简洁解析"},
    "error_reason": {"type": "string", "description": "错误原因，非错误时为空字符串"},
    "knowledge_points": {"type": "array", "items": {"type": "string"},
                         "description": "1~5 个知识点"},
    "confidence": {"type": ["number", "null"],
                   "description": "0~1 的置信度；无法评估时为 null，不要编造"},
}


def _question_schema(depth):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(_FIELDS) + ["children"],
        "properties": {**{k: dict(v) for k, v in _FIELDS.items()}},
    }
    schema["properties"]["children"] = (
        {"type": "array", "items": _question_schema(depth - 1)}
        if depth > 1 else
        {"type": "array", "maxItems": 0, "description": "最深层必须为空数组"}
    )
    return schema


RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "page_summary", "questions"],
    "properties": {
        "subject": {"type": "string", "description": "学科，如 高等数学"},
        "page_summary": {
            "type": "object",
            "additionalProperties": False,
            "required": ["recognized_questions", "correct", "incorrect", "undetermined"],
            "properties": {
                "recognized_questions": {"type": "integer"},
                "correct": {"type": "integer"},
                "incorrect": {"type": "integer"},
                "undetermined": {"type": "integer"},
            },
        },
        "questions": {"type": "array", "items": _question_schema(MAX_QUESTION_DEPTH)},
    },
}

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "exam_marking_result",
        "description": "大学课程试卷的逐题批改结果",
        "schema": RESPONSE_SCHEMA,
        "strict": True,
    },
}


def build_payload(model, image_png):
    """Pure request construction so the wire format can be asserted in tests."""
    encoded = base64.b64encode(image_png).decode("ascii")
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                {"type": "text", "text": USER_PROMPT},
            ]},
        ],
        "response_format": RESPONSE_FORMAT,
    }


def extract_content(body):
    """Pull the assistant text out of a DashScope OpenAI-compatible response."""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("qwen:BadResponse", "千问未返回任何结果")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # some deployments return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("qwen:BadResponse", "千问返回了空结果")
    return content


def parse_structured(content):
    """Strictly parse the JSON the model returned. A failure fails the page."""
    text = content.strip()
    if text.startswith("```"):  # defensive: the prompt forbids fences
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1] if "{" in text else text
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        raise ProviderError("qwen:BadResponse", "千问返回的内容不是合法 JSON，未生成分数") from None
    if not isinstance(payload, dict):
        raise ProviderError("qwen:BadResponse", "千问返回的内容结构不是对象")
    try:
        return normalize_qwen_result(payload)
    except ValueError as exc:
        raise ProviderError("qwen:EmptyResult", str(exc)) from None


class QwenMarkingProvider:
    name = "qwen"
    async_remote = False  # one synchronous call yields the finished result

    def __init__(self, settings, http_client=None):
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=settings.qwen_marking_timeout)

    def readiness(self):
        return dict(self._settings.marking_readiness())

    def ensure_ready(self):
        mode, provider = self._settings.resolve_marking()
        if mode == "disabled":
            raise ProviderError("MarkingDisabled", "试卷批改尚未启用")
        if provider != "qwen":
            raise ProviderError("ProviderMismatch", "当前配置的批改服务不是千问")
        if not self._settings.has_dashscope_credentials:
            raise ProviderError("qwen:NotConfigured",
                                "千问视觉批改尚未配置，请联系管理员设置 DASHSCOPE_API_KEY")

    def _raise_for_http(self, response):
        if response.status_code == 200:
            return
        code = "qwen:HttpError"
        detail = ""
        try:
            error = response.json().get("error") or {}
            detail = str(error.get("code") or "")
        except ValueError:
            error = {}
        if response.status_code == 401:
            code = "qwen:Unauthorized"
        elif response.status_code == 429:
            code = "qwen:RateLimited"
        elif response.status_code == 402 or "quota" in detail or "balance" in detail:
            code = "qwen:InsufficientBalance"
        elif response.status_code == 404 or "model" in detail.lower():
            code = "qwen:ModelNotFound"
        request_id = response.headers.get("x-request-id")
        from .base import provider_message
        raise ProviderError(code, provider_message(code), request_id)

    def submit(self, image, reference=None):
        """Perform the whole call. `reference` is accepted for interface parity and
        deliberately unused: the assistant-answer image path is a Tencent-only
        capability that has not been verified for this model."""
        self.ensure_ready()
        payload = build_payload(self._settings.qwen_marking_model, image)
        started = time.monotonic()
        try:
            response = self._http.post(
                f"{self._settings.dashscope_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.dashscope_api_key}",
                         "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.ConnectError as exc:
            # The request never reached the model, so this is a definite failure.
            raise ProviderError("qwen:NetworkError", "无法连接千问接口", None, uncertain=False) from exc
        except httpx.TimeoutException as exc:
            # It may have run and been billed; never auto-resubmit.
            raise ProviderError("qwen:Timeout", "千问接口响应超时", None, uncertain=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("qwen:NetworkError", "千问接口请求失败", None, uncertain=True) from exc
        latency_ms = (time.monotonic() - started) * 1000
        self._raise_for_http(response)
        try:
            body = response.json()
        except ValueError:
            raise ProviderError("qwen:BadResponse", "千问返回的内容无法解析") from None
        result = parse_structured(extract_content(body))
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
        return ProviderOutcome(
            state="succeeded", result=result, raw=body,
            request_id=response.headers.get("x-request-id") or body.get("id"),
            usage=usage, latency_ms=round(latency_ms, 1),
            model=body.get("model") or self._settings.qwen_marking_model,
        )

    def get_result(self, provider_job_id):
        # Synchronous provider: there is no remote job to poll.
        raise ProviderError("ProviderMismatch", "千问批改为同步调用，没有可轮询的远端任务")
