"""File logging for the backend.

Without this, the only record of a failure is the uvicorn console. When an agent
turn raises, the router logs the traceback and that window is the only place it
exists — close it and the evidence is gone. A rotating file keeps it.

Configured once per log directory; see `configure_logging`.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# backend/logs — next to the app package, not inside it.
DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE_NAME = "app.log"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def resolve_log_dir(log_dir=None) -> Path:
    """Explicit argument wins, then $LOG_DIR, then backend/logs."""
    if log_dir is not None:
        return Path(log_dir)
    return Path(os.getenv("LOG_DIR") or DEFAULT_LOG_DIR)


def configure_logging(log_dir=None, level: str | None = None) -> Path:
    """Attach a rotating file handler to the root logger; return the log path.

    Idempotent for a given directory: calling it again returns the existing path
    instead of attaching a second handler, which would write every line twice.
    """
    directory = resolve_log_dir(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE_NAME

    root = logging.getLogger()
    target = path.resolve()
    for handler in root.handlers:
        if not isinstance(handler, RotatingFileHandler):
            continue
        try:
            if Path(handler.baseFilename).resolve() == target:
                return path
        except OSError:  # a handler whose file is already gone is not a match
            continue

    handler = RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level or os.getenv("LOG_LEVEL", "INFO"))
    return path
