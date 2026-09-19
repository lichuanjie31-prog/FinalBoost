import os
from dataclasses import dataclass, field
from pathlib import Path


def real_secret(value):
    """Treat documented placeholder values as unset, so readiness never lies.

    `.env.example` ships values like `your-api-key`; without this a fresh clone
    would report marking as configured and then fail with a 401 at call time.
    """
    value = (value or "").strip()
    if value.lower().startswith(("your-", "your_", "example", "changeme")) or value.startswith("<"):
        return ""
    return value


@dataclass
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("DATA_DIR", Path(__file__).resolve().parents[1] / "data")
        )
    )
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    grading_mode: str = field(default_factory=lambda: os.getenv("GRADING_MODE", "disabled"))
    mock_scenario: str = field(default_factory=lambda: os.getenv("MOCK_SCENARIO", "success"))
    job_seconds: float = field(default_factory=lambda: float(os.getenv("JOB_SECONDS", "3")))
    job_timeout: float = field(default_factory=lambda: float(os.getenv("JOB_TIMEOUT", "120")))
    # Exam marking. Credentials are read from the backend environment only; they are
    # never exposed through the API, the browser, the database or the logs.
    #   MARKING_MODE      disabled | fixture | live
    #                     (legacy: a bare `qwen`/`tencent` still selects that provider live)
    #   MARKING_PROVIDER  qwen | tencent
    marking_mode: str = field(default_factory=lambda: os.getenv("MARKING_MODE", "disabled"))
    marking_provider: str = field(default_factory=lambda: os.getenv("MARKING_PROVIDER", "qwen"))
    # Qwen VL via DashScope's OpenAI-compatible endpoint. Reuses the project's
    # existing Alibaba credentials rather than inventing a second config system.
    dashscope_api_key: str = field(
        default_factory=lambda: real_secret(os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("EMBEDDING_API_KEY", ""))
    )
    dashscope_base_url: str = field(
        default_factory=lambda: (
            os.getenv("DASHSCOPE_BASE_URL", "") or os.getenv("EMBEDDING_BASE_URL", "")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
    )
    qwen_marking_model: str = field(default_factory=lambda: os.getenv("QWEN_MARKING_MODEL", "qwen3-vl-plus"))
    qwen_marking_timeout: float = field(
        default_factory=lambda: float(os.getenv("QWEN_MARKING_TIMEOUT", "120"))
    )
    tencent_secret_id: str = field(default_factory=lambda: os.getenv("TENCENTCLOUD_SECRET_ID", ""))
    tencent_secret_key: str = field(default_factory=lambda: os.getenv("TENCENTCLOUD_SECRET_KEY", ""))
    tencent_token: str = field(default_factory=lambda: os.getenv("TENCENTCLOUD_TOKEN", ""))
    tencent_region: str = field(default_factory=lambda: os.getenv("TENCENTCLOUD_REGION", "ap-guangzhou"))
    tencent_ocr_endpoint: str = field(
        default_factory=lambda: os.getenv("TENCENTCLOUD_OCR_ENDPOINT", "ocr.tencentcloudapi.com")
    )
    # The vendor allows 10 submitted images per minute; 6s spacing keeps us inside it.
    marking_submit_interval: float = field(
        default_factory=lambda: float(os.getenv("MARKING_SUBMIT_INTERVAL", "6"))
    )
    # Query pacing. Independent of the submit limit so acceptance runs can poll faster.
    marking_poll_interval: float = field(
        default_factory=lambda: float(os.getenv("MARKING_POLL_INTERVAL", "6"))
    )
    marking_request_timeout: float = field(
        default_factory=lambda: float(os.getenv("MARKING_REQUEST_TIMEOUT", "30"))
    )
    access_seconds: float = 900
    refresh_seconds: float = 604800
    origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            os.getenv(
                "ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
            ).split(",")
        )
    )
    admin_usernames: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            name.strip().lower()
            for name in os.getenv("ADMIN_USERNAMES", "").split(",")
            if name.strip()
        )
    )

    # LLM configuration
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "60")))

    # Optional image-capable model for grading, independent of the chat model.
    grading_api_key: str = field(default_factory=lambda: os.getenv("GRADING_API_KEY", ""))
    grading_model: str = field(default_factory=lambda: os.getenv("GRADING_MODEL", ""))
    grading_base_url: str = field(default_factory=lambda: os.getenv("GRADING_BASE_URL", ""))

    # MySQL configuration
    mysql_host: str = field(default_factory=lambda: os.getenv("MYSQL_HOST", "localhost"))
    mysql_port: int = field(default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")))
    mysql_database: str = field(default_factory=lambda: os.getenv("MYSQL_DATABASE", "finalboost"))
    mysql_user: str = field(default_factory=lambda: os.getenv("MYSQL_USER", "root"))
    mysql_password: str = field(default_factory=lambda: os.getenv("MYSQL_PASSWORD", ""))

    # RAG configuration
    rag_enabled: bool = field(default_factory=lambda: os.getenv("RAG_ENABLED", "true").lower() == "true")
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "finalboost_chunks"))
    embedding_base_url: str = field(default_factory=lambda: os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    embedding_api_key: str = field(default_factory=lambda: os.getenv("EMBEDDING_API_KEY", ""))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-v4"))
    embedding_dimensions: int = field(default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSIONS", "1024")))

    def validate(self):
        self.data_dir = Path(self.data_dir).resolve()
        if self.grading_mode not in {"mock", "llm"}:
            raise RuntimeError(
                "Set GRADING_MODE=mock or GRADING_MODE=llm for local development. "
                "A real grading adapter is not implemented for other modes."
            )
        if self.grading_mode == "llm" and not (self.grading_api_key or self.llm_api_key):
            raise RuntimeError(
                "GRADING_MODE=llm requires LLM_API_KEY to be set. "
                "Get your API key from https://platform.deepseek.com"
            )
        if self.environment == "production":
            raise RuntimeError(
                "Production startup is disabled until a verified real grading adapter is configured."
            )
        if self.mock_scenario not in {"success", "unreadable", "provider_error", "timeout"}:
            raise RuntimeError("Invalid MOCK_SCENARIO")
        if min(self.job_seconds, self.job_timeout, self.access_seconds, self.refresh_seconds) <= 0:
            raise RuntimeError("Durations must be positive")
        if self.marking_mode not in {"disabled", "fixture", "live", "qwen", "tencent"}:
            raise RuntimeError("MARKING_MODE must be one of disabled, fixture, live, qwen, tencent")
        if self.marking_provider not in {"qwen", "tencent"}:
            raise RuntimeError("MARKING_PROVIDER must be qwen or tencent")
        if min(self.marking_submit_interval, self.marking_poll_interval, self.marking_request_timeout,
               self.qwen_marking_timeout) <= 0:
            raise RuntimeError("Marking durations must be positive")
        configured_admins = self.admin_usernames.split(",") if isinstance(self.admin_usernames, str) else self.admin_usernames
        self.admin_usernames = tuple(dict.fromkeys(name.strip().lower() for name in configured_admins if name.strip()))


    @property
    def secure_cookie(self):
        return self.environment == "production"

    @property
    def has_tencent_credentials(self):
        return bool(self.tencent_secret_id and self.tencent_secret_key)

    @property
    def has_dashscope_credentials(self):
        return bool(self.dashscope_api_key)

    def resolve_marking(self):
        """Return (mode, provider); mode is disabled | fixture | live.

        A bare `MARKING_MODE=qwen|tencent` is the legacy spelling and selects that
        provider running live, so existing deployments keep working unchanged.
        """
        if self.marking_mode in ("qwen", "tencent"):
            return "live", self.marking_mode
        if self.marking_mode == "live":
            return "live", self.marking_provider
        if self.marking_mode == "fixture":
            return "fixture", self.marking_provider
        return "disabled", self.marking_provider

    def marking_readiness(self):
        """Describe marking availability without ever echoing credential material."""
        mode, provider = self.resolve_marking()
        base = {"mode": mode, "provider": provider,
                "model": self.qwen_marking_model if provider == "qwen" else None,
                "region": self.tencent_region if provider == "tencent" else None}
        if mode == "disabled":
            return {**base, "configured": False, "reason": "MarkingDisabled",
                    "message": "试卷批改尚未启用；本机为演示模式，不识别图片内容。"}
        if mode == "fixture":
            return {**base, "configured": True, "reason": None,
                    "submitIntervalSeconds": self.marking_submit_interval,
                    "message": f"离线验收模式：{provider} 的外部边界由本地桩替代，未发生真实调用。"}
        if provider == "qwen":
            if not self.has_dashscope_credentials:
                return {**base, "configured": False, "reason": "NotConfigured",
                        "message": "千问视觉批改尚未配置，请在后端设置 DASHSCOPE_API_KEY。"}
            return {**base, "configured": True, "reason": None,
                    "submitIntervalSeconds": self.marking_submit_interval,
                    "message": f"千问视觉批改已配置（{self.qwen_marking_model}）。"}
        if not self.has_tencent_credentials:
            return {**base, "configured": False, "reason": "NotConfigured",
                    "message": "尚未配置腾讯云凭据，请在后端设置 TENCENTCLOUD_SECRET_ID 与 TENCENTCLOUD_SECRET_KEY。"}
        return {**base, "configured": True, "reason": None,
                "submitIntervalSeconds": self.marking_submit_interval,
                "message": "腾讯云批改已配置。"}
