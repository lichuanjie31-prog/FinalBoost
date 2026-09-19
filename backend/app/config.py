import os
from dataclasses import dataclass, field
from pathlib import Path


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
    # Tencent Cloud question-marking Agent. Credentials are read from the backend
    # environment only; they are never exposed through the API or the browser.
    #   disabled -> marking endpoints report "not configured"
    #   fixture  -> offline acceptance: a local stub replaces the Tencent SDK boundary
    #   tencent  -> real SDK calls, requires TENCENTCLOUD_SECRET_ID/SECRET_KEY
    marking_mode: str = field(default_factory=lambda: os.getenv("MARKING_MODE", "disabled"))
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
        if self.marking_mode not in {"disabled", "fixture", "tencent"}:
            raise RuntimeError("MARKING_MODE must be one of disabled, fixture, tencent")
        if min(self.marking_submit_interval, self.marking_poll_interval, self.marking_request_timeout) <= 0:
            raise RuntimeError("Marking durations must be positive")

    @property
    def secure_cookie(self):
        return self.environment == "production"

    @property
    def has_tencent_credentials(self):
        return bool(self.tencent_secret_id and self.tencent_secret_key)

    def marking_readiness(self):
        """Describe marking availability without ever echoing credential material."""
        if self.marking_mode == "disabled":
            return {
                "mode": "disabled",
                "configured": False,
                "reason": "MarkingDisabled",
                "message": "腾讯云批改尚未启用；本机为演示模式，不识别图片内容。",
            }
        if self.marking_mode == "fixture":
            return {
                "mode": "fixture",
                "configured": True,
                "reason": None,
                "region": self.tencent_region,
                "submitIntervalSeconds": self.marking_submit_interval,
                "message": "离线验收模式：腾讯云边界由本地桩替代，未发生真实调用。",
            }
        if not self.has_tencent_credentials:
            return {
                "mode": "tencent",
                "configured": False,
                "reason": "NotConfigured",
                "region": self.tencent_region,
                "message": "尚未配置腾讯云凭据，请在后端设置 TENCENTCLOUD_SECRET_ID 与 TENCENTCLOUD_SECRET_KEY。",
            }
        return {
            "mode": "tencent",
            "configured": True,
            "reason": None,
            "region": self.tencent_region,
            "submitIntervalSeconds": self.marking_submit_interval,
            "message": "腾讯云批改已配置。",
        }
