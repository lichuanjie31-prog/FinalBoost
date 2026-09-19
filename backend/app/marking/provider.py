"""Tencent SDK boundary. No implicit retry of chargeable submissions.

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
import io
import json
from PIL import Image, ImageOps, UnidentifiedImageError

# Verified QuestionConfigMap switches. DisableAnswerAnalysis is deliberately absent:
# we always want the answer analysis text.
QUESTION_CONFIG = {
    "KnowledgePoints": True,   # 输出每道题的知识点
    "TrueAnswer": True,        # 输出每道题的正确答案
    "StepCorrection": True,    # 启用步骤级批改
    "OutputSubQuestionsAndCoords": True,  # 输出子题干和插图坐标
}

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_BASE64_BYTES = 10_000_000
MAX_ASSIST_IMAGES = 2


class ProviderError(Exception):
    def __init__(self, code, message, request_id=None, uncertain=False):
        super().__init__(message)
        self.code, self.request_id, self.uncertain = code, request_id, uncertain


def prepare_image(content):
    # Pillow cannot decode PDF and reports it as an unidentified file, so detect
    # it up front to give the user an actionable message.
    if content[:5] == b"%PDF-":
        raise ValueError("本轮暂不支持 PDF，请先转为 JPEG 或 PNG 图片后上传")
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.load()
            if img.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("仅支持 JPEG、PNG、WebP")
            # Normalize EXIF orientation and WebP to the same PNG used for coordinates.
            normalized = ImageOps.exif_transpose(img).convert("RGB")
            out = io.BytesIO()
            normalized.save(out, format="PNG")
            data = out.getvalue()
            size = normalized.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("文件不是有效的 JPEG、PNG 或 WebP 图片") from None
    if len(base64.b64encode(data)) > MAX_BASE64_BYTES:
        raise ValueError("转换后 Base64 超过 10MB，请缩小图片后重新上传")
    return data, size


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
    def __init__(self, settings, client=None):
        self._settings = settings
        self._client = client

    def readiness(self):
        state = dict(self._settings.marking_readiness())
        if state["configured"] and self._settings.marking_mode == "tencent" and self._client is None:
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
        if settings.marking_mode == "disabled":
            raise ProviderError("MarkingDisabled", "腾讯云批改尚未启用")
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
                code, "腾讯云请求未完成，请根据错误码和 RequestId 排查", exc.get_request_id(),
                uncertain=code.startswith(("ClientNetworkError", "InternalError")) or "Timeout" in code,
            ) from None

    def submit(self, image, reference=None):
        return self._call("SubmitQuestionMarkAgentJob", build_submit_params(image, reference))

    def describe(self, job_id):
        return self._call("DescribeQuestionMarkAgentJob", {"JobId": job_id})
