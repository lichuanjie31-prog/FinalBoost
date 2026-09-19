"""Tencent Cloud question-marking Agent provider.

Field names below were verified against the installed SDK
(tencentcloud-sdk-python-ocr 3.1.175, tencentcloud/ocr/v20181119/models.py)
rather than recalled from memory:

* SubmitQuestionMarkAgentJobRequest: ImageBase64, ImageUrl, PdfPageNumber,
  BoolSingleQuestion (deprecated), EnableDeepThink (deprecated), QuestionConfigMap,
  ReferenceAnswer (single-question text only), ImageBase64List/ImageUrlList,
  AssistMarkType (0 no assist, 1 single-question text assist, 2 whole-page assist),
  AnswerAssistMap.
* Submit response: JobId, QuestionInfo, QuestionCount, OriginalImageUrl, RequestId.
* Describe response: ErrorCode, ErrorMessage, JobStatus (WAIT/RUN/FAIL/DONE),
  Angle, MarkInfos, RequestId.

ImageBase64List carries the *answer paper* when AssistMarkType=2 (at most two
images). When AssistMarkType is anything else those same images are stitched
together to join a single question across pages — a behaviour this project does
not use, because each uploaded page becomes its own job.
"""
import base64
import json

from .base import (ALLOWED_IMAGE_FORMATS, MAX_ASSIST_IMAGES, MAX_BASE64_BYTES,  # noqa: F401
                   ProviderError, ProviderOutcome, provider_message, prepare_image)
from .models import normalize_result

__all__ = ["ALLOWED_IMAGE_FORMATS", "MAX_ASSIST_IMAGES", "MAX_BASE64_BYTES", "ProviderError",
           "ProviderOutcome", "QUESTION_CONFIG", "TencentMarkingProvider", "build_submit_params",
           "prepare_image", "provider_message"]

# Verified QuestionConfigMap switches. DisableAnswerAnalysis is deliberately absent:
# we always want the answer analysis text.
QUESTION_CONFIG = {
    "KnowledgePoints": True,   # 输出每道题的知识点
    "TrueAnswer": True,        # 输出每道题的正确答案
    "StepCorrection": True,    # 启用步骤级批改
    "OutputSubQuestionsAndCoords": True,  # 输出子题干和插图坐标
}


def build_submit_params(image, reference=None):
    """Pure request construction so tests can assert the SDK boundary exactly."""
    params = {
        "ImageBase64": base64.b64encode(image).decode("ascii"),
        "QuestionConfigMap": json.dumps(QUESTION_CONFIG),
    }
    if reference is not None:
        # AssistMarkType=2 hands the vendor an answer paper alongside the student
        # page. Unlike other values it never triggers cross-page stitching.
        params["AssistMarkType"] = 2
        params["ImageBase64List"] = [base64.b64encode(reference).decode("ascii")][:MAX_ASSIST_IMAGES]
    return params


class TencentMarkingProvider:
    name = "tencent"
    async_remote = True

    def __init__(self, settings, client=None):
        self._settings = settings
        self._client = client

    def readiness(self):
        state = dict(self._settings.marking_readiness())
        mode, provider = self._settings.resolve_marking()
        if state["configured"] and mode == "live" and provider == "tencent" and self._client is None:
            try:
                import tencentcloud.ocr.v20181119  # noqa: F401
            except ImportError:
                state.update(configured=False, reason="MissingDependency",
                             message="缺少腾讯云 SDK，请安装 backend/requirements-marking.txt")
        return state

    def ensure_ready(self):
        if self._client is not None:
            return
        settings = self._settings
        mode, provider = settings.resolve_marking()
        if mode == "disabled":
            raise ProviderError("MarkingDisabled", "试卷批改尚未启用")
        if provider != "tencent":
            raise ProviderError("ProviderMismatch", "当前配置的批改服务不是腾讯云")
        if not settings.has_tencent_credentials:
            raise ProviderError(
                "NotConfigured",
                "尚未配置腾讯云凭据，请联系管理员设置 TENCENTCLOUD_SECRET_ID 与 TENCENTCLOUD_SECRET_KEY",
            )
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.ocr.v20181119.ocr_client import OcrClient
        except ImportError:
            raise ProviderError("MissingDependency", "请安装 backend/requirements-marking.txt") from None
        profile = ClientProfile()
        profile.httpProfile = HttpProfile(
            endpoint=settings.tencent_ocr_endpoint, reqTimeout=settings.marking_request_timeout
        )
        self._client = OcrClient(
            credential.Credential(settings.tencent_secret_id, settings.tencent_secret_key,
                                  settings.tencent_token or None),
            settings.tencent_region, profile,
        )

    def _call(self, action, params):
        self.ensure_ready()
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
        from tencentcloud.ocr.v20181119 import models
        request = getattr(models, action + "Request")()
        request.from_json_string(json.dumps(params))
        try:
            return json.loads(getattr(self._client, action)(request).to_json_string())
        except TencentCloudSDKException as exc:
            code = exc.get_code() or "ProviderError"
            # Preserve machine code/request ID, not vendor messages which may echo inputs.
            raise ProviderError(
                code, provider_message(code), exc.get_request_id(),
                uncertain=code.startswith(("ClientNetworkError", "InternalError")) or "Timeout" in code,
            ) from None

    def submit(self, image, reference=None):
        """Create the remote job. Returns a pending outcome carrying its id."""
        response = self._call("SubmitQuestionMarkAgentJob", build_submit_params(image, reference))
        remote_id = response.get("JobId")
        if not isinstance(remote_id, str) or not remote_id:
            # The vendor may or may not have accepted the job, so callers must not
            # resubmit automatically.
            raise ProviderError("SubmissionUnknown",
                                "提交结果未知，请勿自动重新提交。需核对供应商任务，避免重复计费。",
                                response.get("RequestId"), uncertain=True)
        return ProviderOutcome(state="queued", provider_job_id=remote_id,
                               request_id=response.get("RequestId"), raw=response)

    def get_result(self, provider_job_id):
        raw = self._call("DescribeQuestionMarkAgentJob", {"JobId": provider_job_id})
        status = raw.get("JobStatus")
        common = {"raw": raw, "request_id": raw.get("RequestId")}
        if status in ("WAIT", "RUN"):
            # WAIT and RUN are distinct states for the user, so keep them distinct.
            return ProviderOutcome(state="running" if status == "RUN" else "queued", **common)
        if status == "FAIL":
            code = str(raw.get("ErrorCode") or "ProviderFailed")
            return ProviderOutcome(state="failed", error={
                "code": code,
                "message": provider_message(code, str(raw.get("ErrorMessage") or "腾讯云批改失败，请按错误码和 RequestId 排查")),
            }, **common)
        if status != "DONE":
            return ProviderOutcome(state="failed", error={
                "code": "InvalidProviderStatus", "message": "供应商返回未知状态"}, **common)
        try:
            result = normalize_result(raw)
        except (ValueError, TypeError, AttributeError):
            return ProviderOutcome(state="failed", error={
                "code": "InvalidProviderResult", "message": "批改结果不完整，未生成分数，请人工核对"}, **common)
        return ProviderOutcome(state="succeeded", result=result, **common)
