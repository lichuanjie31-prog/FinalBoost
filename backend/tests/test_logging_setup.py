"""Tracebacks must reach a file, not just the terminal.

A 502 whose traceback only existed in the uvicorn console was unrecoverable
once the window closed. These tests pin the log file behaviour.
"""
import logging

import pytest

from app.logging_setup import configure_logging


@pytest.fixture
def clean_root_handlers():
    """configure_logging mutates the root logger; undo it so tests stay isolated."""
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(before_level)


def test_writes_tracebacks_to_a_file(tmp_path, clean_root_handlers):
    log_path = configure_logging(log_dir=tmp_path)

    assert log_path.exists()

    try:
        raise ValueError("boom-marker")
    except ValueError:
        logging.getLogger("app.somewhere").exception("Agent turn failed")

    contents = log_path.read_text(encoding="utf-8")
    assert "Agent turn failed" in contents
    assert "ValueError: boom-marker" in contents


def test_is_idempotent_for_the_same_directory(tmp_path, clean_root_handlers):
    """Repeated app construction must not stack handlers and duplicate every line."""
    first = configure_logging(log_dir=tmp_path)
    configure_logging(log_dir=tmp_path)

    logging.getLogger("app.somewhere").error("only-once-marker")

    assert first.read_text(encoding="utf-8").count("only-once-marker") == 1


def test_returns_the_same_path_when_called_again(tmp_path, clean_root_handlers):
    assert configure_logging(log_dir=tmp_path) == configure_logging(log_dir=tmp_path)


def test_app_still_starts_when_the_log_directory_is_unusable(tmp_path, monkeypatch,
                                                            clean_root_handlers):
    """Logging must never be the reason the backend refuses to boot."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("this is a file, so mkdir will fail", encoding="utf-8")
    monkeypatch.setenv("LOG_DIR", str(blocker))

    with TestClient(create_app(data_dir=tmp_path, grading_mode="mock"), raise_server_exceptions=False) as client:
        assert client.get("/api/v1/health").status_code == 200
