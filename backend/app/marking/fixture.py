"""Offline stand-in for the Tencent SDK boundary (MARKING_MODE=fixture).

It implements exactly the two provider methods the service calls, so the rest of
the pipeline — persistence, pacing, idempotency, polling, result mapping and the
browser UI — runs unmodified against a real backend. No network call is made and
no credential is required.

The active scenario is read on every call, so an acceptance script can force a
vendor failure and then recover without restarting the server:

    MARKING_FIXTURE_SCENARIO   initial scenario (default "success")
    MARKING_FIXTURE_CONTROL    JSON file {"scenario": "..."} that overrides it
    MARKING_FIXTURE_STAGES     describe calls spent in WAIT/RUN before DONE (default 2)
"""
import json
import os
import time

from .provider import ProviderError

SCENARIOS = {"success", "provider_error", "submit_timeout", "empty_result"}

_ANALYSIS = [
    {
        "MarkItemTitle": "第 1 题 求不定积分",
        "QuestionPositions": [40, 60, 460, 60, 460, 220, 40, 220],
        "RightAnswer": "x^2/2 + C",
        "Subject": "数学",
        "QuestionType": "计算题",
        "AnswerInfos": [
            {
                "HandwriteInfo": "x^2/2",
                "IsCorrect": False,
                "AnswerAnalysis": "漏写积分常数 C，属于概念性遗漏。",
                "HandwriteInfoPositions": [60, 140, 300, 140, 300, 190, 60, 190],
                "RightAnswer": "x^2/2 + C",
                "KnowledgePoints": ["不定积分", "积分常数"],
            }
        ],
        "MarkInfos": [
            {
                "MarkItemTitle": "第 1 题 第 (1) 问",
                "QuestionPositions": [40, 100, 460, 100, 460, 160, 40, 160],
                "RightAnswer": "x^2/2 + C",
                "AnswerInfos": [
                    {
                        "HandwriteInfo": "x^2/2 + C",
                        "IsCorrect": True,
                        "AnswerAnalysis": "过程与结果均正确。",
                        "HandwriteInfoPositions": [60, 120, 280, 120, 280, 150, 60, 150],
                        "RightAnswer": "x^2/2 + C",
                        "KnowledgePoints": ["不定积分"],
                    }
                ],
            }
        ],
    },
    {
        "MarkItemTitle": "第 2 题 判断级数敛散性",
        "QuestionPositions": [40, 260, 460, 260, 460, 420, 40, 420],
        "RightAnswer": "发散",
        "Subject": "数学",
        "QuestionType": "判断题",
        "AnswerInfos": [
            {
                "HandwriteInfo": "收敛",
                "IsCorrect": False,
                "AnswerAnalysis": "调和级数发散，通项趋于零不能推出级数收敛。",
                "HandwriteInfoPositions": [60, 340, 300, 340, 300, 390, 60, 390],
                "RightAnswer": "发散",
                "KnowledgePoints": ["级数敛散性", "调和级数"],
            }
        ],
    },
]


class FixtureMarkingProvider:
    """Deterministic vendor stub. Never contacts Tencent Cloud."""

    def __init__(self, settings):
        self._settings = settings
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
            # Uncertain: the vendor may or may not have accepted the job, so the
            # service must not resubmit automatically.
            raise ProviderError("ClientNetworkError", "腾讯云请求未完成", None, uncertain=True)
        self._counter += 1
        job_id = f"fixture-job-{self._counter}"
        self._jobs[job_id] = {"polls": 0, "at": time.time()}
        return {
            "JobId": job_id,
            "QuestionCount": str(len(_ANALYSIS)),
            "OriginalImageUrl": "",
            "RequestId": f"fixture-submit-{self._counter}",
        }

    def describe(self, job_id):
        state = self._jobs.setdefault(job_id, {"polls": 0, "at": time.time()})
        scenario = self.scenario()
        if scenario == "provider_error":
            return self._envelope(job_id, JobStatus="FAIL", ErrorCode="FailedOperation.ImageNotSupported",
                                  ErrorMessage="图片无法识别")
        state["polls"] += 1
        if state["polls"] <= self._stages():
            status = "WAIT" if state["polls"] == 1 else "RUN"
            return self._envelope(job_id, JobStatus=status)
        if scenario == "empty_result":
            return self._envelope(job_id, JobStatus="DONE", MarkInfos=[])
        return self._envelope(job_id, JobStatus="DONE", Angle=0, MarkInfos=json.loads(json.dumps(_ANALYSIS)))

    @staticmethod
    def _envelope(job_id, **fields):
        payload = {"ErrorCode": "", "ErrorMessage": "", "JobStatus": "WAIT", "Angle": None, "MarkInfos": None}
        payload.update(fields)
        payload["RequestId"] = f"fixture-query-{job_id}"
        return payload
