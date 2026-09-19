"""Provider-neutral marking boundary.

Everything here is shared by every provider: the image preparation rules, the
error type that carries a machine code plus a safe user-facing message, and the
small outcome record the service persists. Providers themselves only know how to
hand an image to a model and turn the answer into the unified result DTO.

Adding a provider must never require touching the service, the router, the
database schema or the frontend.
"""
import base64
import io
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_BASE64_BYTES = 10_000_000
MAX_ASSIST_IMAGES = 2

# Vendor codes that deserve a specific, actionable message. Only codes listed here
# are ever surfaced verbatim-adjacent; anything else falls back to the generic
# text, so a vendor message that echoes our input can never reach the user.
ACTIONABLE_CODES = {
    "FailedOperation.UnOpenError": "腾讯云试题批改服务尚未开通，请前往腾讯云控制台开通「文字识别 · 试题批改」后重试",
    "AuthFailure.SecretIdNotFound": "腾讯云 SecretId 无效，请检查后端凭据配置",
    "AuthFailure.SignatureFailure": "腾讯云签名校验失败，请检查后端 SecretKey 是否正确",
    "AuthFailure.TokenFailure": "腾讯云临时 Token 无效或已过期，请重新获取",
    "FailedOperation.InsufficientBalance": "腾讯云账户余额不足，请充值后重试",
    "RequestLimitExceeded": "腾讯云请求过于频繁，请稍后重试",
    "qwen:NotConfigured": "千问视觉批改尚未配置，请在后端设置 DASHSCOPE_API_KEY",
    "qwen:Unauthorized": "千问 API Key 无效或已过期，请检查 DASHSCOPE_API_KEY",
    "qwen:RateLimited": "千问接口请求过于频繁，请稍后重试",
    "qwen:InsufficientBalance": "千问账户余额不足或未开通该模型，请前往百炼控制台检查",
    "qwen:ModelNotFound": "千问模型不可用，请检查 QWEN_MARKING_MODEL 是否为账号已开通的模型",
    "qwen:Timeout": "千问接口响应超时，请稍后重新提交该页",
    "qwen:NetworkError": "无法连接千问接口，请检查网络后重新提交该页",
    "qwen:BadResponse": "千问返回的内容不是可用的批改结果，未生成分数，请人工核对",
    "qwen:EmptyResult": "千问未识别出任何题目，请确认图片清晰且包含题目后重新提交",
}

GENERIC_MESSAGE = "批改服务请求未完成，请根据错误码和 RequestId 排查"


class ProviderError(Exception):
    def __init__(self, code, message, request_id=None, uncertain=False):
        super().__init__(message)
        self.code, self.request_id, self.uncertain = code, request_id, uncertain


def provider_message(code, fallback=GENERIC_MESSAGE):
    return ACTIONABLE_CODES.get(code, fallback)


def prepare_image(content):
    """Normalize an upload to the PNG every provider receives. Returns (bytes, (w, h))."""
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
    except (UnidentifiedImageError, OSError):
        raise ValueError("文件不是有效的 JPEG、PNG 或 WebP 图片") from None
    if len(base64.b64encode(data)) > MAX_BASE64_BYTES:
        raise ValueError("转换后 Base64 超过 10MB，请缩小图片后重新上传")
    return data, size


@dataclass
class ProviderOutcome:
    """What a provider hands back to the service.

    state is one of 'queued' | 'running' | 'succeeded' | 'failed' and maps
    straight onto the job status. result is always the unified MarkingResult dict,
    never a provider-specific shape.
    """
    state: str
    provider_job_id: str | None = None
    result: dict | None = None
    raw: dict | None = None
    error: dict | None = None
    request_id: str | None = None
    usage: dict | None = None
    latency_ms: float | None = None
    model: str | None = None


class MarkingProvider(Protocol):
    """Contract every marking provider implements.

    `async_remote` distinguishes a provider that returns a job id to poll later
    (Tencent) from one whose call yields the finished result directly (Qwen).
    The service keys its persistence and recovery behaviour off that flag, so a
    synchronous model is never dressed up as a fake remote job.
    """

    name: str
    async_remote: bool

    def readiness(self) -> dict: ...

    def ensure_ready(self) -> None: ...

    def submit(self, image, reference=None) -> ProviderOutcome: ...

    def get_result(self, provider_job_id) -> ProviderOutcome: ...
