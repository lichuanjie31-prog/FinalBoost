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

    def validate(self):
        self.data_dir = Path(self.data_dir).resolve()
        if self.grading_mode not in {"mock", "llm"}:
            raise RuntimeError(
                "Set GRADING_MODE=mock or GRADING_MODE=llm for local development. "
                "A real grading adapter is not implemented for other modes."
            )
        if self.grading_mode == "llm" and not self.llm_api_key:
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
        configured_admins = self.admin_usernames.split(",") if isinstance(self.admin_usernames, str) else self.admin_usernames
        self.admin_usernames = tuple(dict.fromkeys(name.strip().lower() for name in configured_admins if name.strip()))

    @property
    def secure_cookie(self):
        return self.environment == "production"
