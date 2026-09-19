"""Offline stand-in for a provider's external boundary (MARKING_MODE=fixture).

It implements the same provider contract, so the service, the database, the HTTP
API, the status machine and the frontend all run unmodified. No network call is
made and no credential is required.

Two shapes, matching the provider it impersonates:

* name == "tencent" — async: submit returns a job id, get_result walks WAIT/RUN/DONE.
* name == "qwen"    — sync:  submit returns the finished result in one shot.

The active scenario is read on every call, so an acceptance script can force a
failure and then recover without restarting the server:

    MARKING_FIXTURE_SCENARIO   initial scenario (default "success")
    MARKING_FIXTURE_CONTROL    JSON file {"scenario": "..."} that overrides it
    MARKING_FIXTURE_STAGES     describe calls spent in WAIT/RUN before DONE (default 2)
"""
import json
import os
import time

from .base import ProviderError, ProviderOutcome
from .models import QWEN_NOTICE

SCENARIOS = {"success", "provider_error", "submit_timeout", "empty_result"}

TENCENT_NOTICE = ('AI 批改需核对；缺少评分细则，未计算分数。'
                  '坐标需结合旋转角度验证后叠加。')

# One dataset shared by both providers, so the frontend renders identical content
# no matter which provider produced it.
_QUESTIONS = [
    {
        "questionId": "1", "text": "第 1 题 求不定积分", "subject": "数学", "questionType": "计算题",
        "polygon": None, "imagePolygons": [], "rightAnswer": "x^2/2 + C",
        "confidence": 0.93, "boundingBox": None,
        "answers": [{
            "answerId": "1.a1", "handwriting": "x^2/2", "correct": False,
            "analysis": "漏写积分常数 C，属于概念性遗漏。", "rightAnswer": "x^2/2 + C",
            "knowledgePoints": ["不定积分", "积分常数"], "errorReason": "漏写积分常数 C",
            "confidence": 0.93, "polygon": None, "boundingBox": None, "score": None, "maxScore": None,
        }],
        "children": [{
            "questionId": "1.1", "text": "第 1 题 第 (1) 问", "subject": "数学", "questionType": "计算题",
            "polygon": None, "imagePolygons": [], "rightAnswer": "x^2/2 + C",
            "confidence": 0.9, "boundingBox": None,
            "answers": [{
                "answerId": "1.1.a1", "handwriting": "x^2/2 + C", "correct": True,
                "analysis": "过程与结果均正确。", "rightAnswer": "x^2/2 + C",
                "knowledgePoints": ["不定积分"], "errorReason": "",
                "confidence": 0.9, "polygon": None, "boundingBox": None, "score": None, "maxScore": None,
            }],
            "children": [],
        }],
    },
    {
        "questionId": "2", "text": "第 2 题 判断级数敛散性", "subject": "数学", "questionType": "判断题",
        "polygon": None, "imagePolygons": [], "rightAnswer": "发散",
        "confidence": 0.88, "boundingBox": None,
        "answers": [{
            "answerId": "2.a1", "handwriting": "收敛", "correct": False,
            "analysis": "调和级数发散，通项趋于零不能推出级数收敛。", "rightAnswer": "发散",
            "knowledgePoints": ["级数敛散性", "调和级数"], "errorReason": "误判调和级数敛散性",
            "confidence": 0.88, "polygon": None, "boundingBox": None, "score": None, "maxScore": None,
        }],
        "children": [],
    },
]


def _unified_result(name):
    qwen = name == "qwen"
    return {
        "questions": json.loads(json.dumps(_QUESTIONS)),
        "angle": 0,
        "subject": "高等数学",
        "totalScore": None,
        "maxScore": None,
        "coordinateSpace": "none" if qwen else "provider_pixels",
        "coordinateAlignmentVerified": False,
        "scoreStatus": "unavailable",
        "notice": QWEN_NOTICE if qwen else TENCENT_NOTICE,
    }


class FixtureMarkingProvider:
    """Deterministic provider stub. Never contacts any external service."""

    def __init__(self, settings, name=None):
        self._settings = settings
        self.name = name or settings.resolve_marking()[1]
        self.async_remote = self.name == "tencent"
        self._jobs = {}
        self._counter = 0

    # -- scenario control -------------------------------------------------
    def scenario(self):
        path = os.getenv("MARKING_FIXTURE_CONTROL")
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    value = json.load(handle).get("scenario")
                if value in SCENARIOS:
                    return value
            except (OSError, ValueError):
                pass
        value = os.getenv("MARKING_FIXTURE_SCENARIO", "success")
        return value if value in SCENARIOS else "success"

    def _stages(self):
        try:
            return max(0, int(os.getenv("MARKING_FIXTURE_STAGES", "2")))
        except ValueError:
            return 2

    # -- provider interface ----------------------------------------------
    def readiness(self):
        return self._settings.marking_readiness()

    def ensure_ready(self):
        return None

    def submit(self, image, reference=None):
        scenario = self.scenario()
        if scenario == "submit_timeout":
            # Uncertain: the provider may or may not have run, so the service must
            # not resubmit automatically.
            code = "ClientNetworkError" if self.async_remote else "qwen:Timeout"
            raise ProviderError(code, "请求未完成，无法确认是否已受理", None, uncertain=True)
        self._counter += 1
        if not self.async_remote:
            return self._sync_outcome(scenario)
        job_id = f"fixture-job-{self._counter}"
        self._jobs[job_id] = {"polls": 0, "at": time.time()}
        return ProviderOutcome(state="queued", provider_job_id=job_id,
                               request_id=f"fixture-submit-{self._counter}",
                               raw={"JobId": job_id, "QuestionCount": str(len(_QUESTIONS))})

    def _sync_outcome(self, scenario):
        if scenario == "provider_error":
            return ProviderOutcome(state="failed", error={
                "code": "qwen:BadResponse", "message": "千问返回的内容不是可用的批改结果，请人工核对"},
                raw={"error": {"code": "invalid_response"}}, request_id="fixture-query-1")
        if scenario == "empty_result":
            return ProviderOutcome(state="failed", error={
                "code": "qwen:EmptyResult", "message": "千问未识别出任何题目"},
                raw={"choices": [{"message": {"content": "{}"}}]}, request_id="fixture-query-1")
        return ProviderOutcome(
            state="succeeded", result=_unified_result(self.name),
            raw={"id": "fixture-completion", "model": self._settings.qwen_marking_model,
                 "choices": [{"message": {"content": "<structured result>"}}]},
            request_id="fixture-query-1",
            usage={"prompt_tokens": 1234, "completion_tokens": 567, "total_tokens": 1801},
            latency_ms=4321.0, model=self._settings.qwen_marking_model)

    def get_result(self, provider_job_id):
        if not self.async_remote:
            raise ProviderError("ProviderMismatch", "同步批改没有可轮询的远端任务")
        state = self._jobs.setdefault(provider_job_id, {"polls": 0, "at": time.time()})
        scenario = self.scenario()
        request_id = f"fixture-query-{provider_job_id}"
        if scenario == "provider_error":
            return ProviderOutcome(state="failed", request_id=request_id,
                                   raw={"JobStatus": "FAIL", "ErrorCode": "FailedOperation.ImageNotSupported"},
                                   error={"code": "FailedOperation.ImageNotSupported", "message": "图片无法识别"})
        state["polls"] += 1
        if state["polls"] <= self._stages():
            status = "WAIT" if state["polls"] == 1 else "RUN"
            return ProviderOutcome(state="queued" if status == "WAIT" else "running",
                                   request_id=request_id, raw={"JobStatus": status})
        if scenario == "empty_result":
            return ProviderOutcome(state="failed", request_id=request_id, raw={"JobStatus": "DONE", "MarkInfos": []},
                                   error={"code": "InvalidProviderResult", "message": "批改结果不完整，未生成分数，请人工核对"})
        return ProviderOutcome(state="succeeded", result=_unified_result(self.name), request_id=request_id,
                               raw={"JobStatus": "DONE", "Angle": 0, "MarkInfos": _QUESTIONS})
