"""The agent 502 must say *why* the model call failed.

A misconfigured provider (key from one vendor, base_url from another) used to
surface as the generic "AI 服务暂时不可用", which sends you debugging the wrong
thing. These tests pin the message to the failure class.
"""
import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.main import create_app

HEADERS = {"X-Requested-With": "FinalBoost", "Origin": "http://127.0.0.1:5173"}
PASSWORD = "Test-password-12345"


def _http_error(cls, status, message):
    """Build a real openai exception carrying an HTTP response, as the SDK raises."""
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status, request=request, json={"error": {"message": message}})
    return cls(message, response=response, body=None)


class _FailingLLM:
    """Stands in for ChatOpenAI; raises on the first model call."""

    def __init__(self, exc):
        self._exc = exc

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, **kwargs):
        raise self._exc


@pytest.fixture
def client_and_login(tmp_path, monkeypatch):
    def _make(exc):
        monkeypatch.setattr(
            "app.agent.router.create_llm_from_settings",
            lambda settings: _FailingLLM(exc),
        )
        app = create_app(data_dir=tmp_path, grading_mode="mock", rag_enabled=False)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        r = client.post("/api/v1/auth/register",
                        json={"username": "student_one", "password": PASSWORD}, headers=HEADERS)
        assert r.status_code == 201, r.text
        auth = {**HEADERS, "Authorization": "Bearer " + r.json()["data"]["accessToken"]}
        return client, auth

    return _make


def test_auth_failure_names_the_credential_mismatch(client_and_login):
    """The exact production failure: a key from vendor A sent to vendor B's endpoint."""
    client, auth = client_and_login(
        _http_error(openai.AuthenticationError, 401, "Incorrect API key provided")
    )
    resp = client.post("/api/v1/agent/chat", json={"message": "你好"}, headers=auth)

    assert resp.status_code == 502
    message = resp.json()["message"]
    assert "LLM_API_KEY" in message
    assert "LLM_BASE_URL" in message


def _connection_error(cls):
    """APIConnectionError and APITimeoutError take a request, not a response."""
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    return cls(request=request)


def test_rate_limit_is_reported_as_such(client_and_login):
    """Quota exhaustion is not an outage: retrying immediately will not help."""
    client, auth = client_and_login(
        _http_error(openai.RateLimitError, 429, "Rate limit reached")
    )
    resp = client.post("/api/v1/agent/chat", json={"message": "你好"}, headers=auth)

    assert resp.status_code == 502
    assert "频繁" in resp.json()["message"] or "额度" in resp.json()["message"]


def test_timeout_is_reported_as_such(client_and_login):
    client, auth = client_and_login(_connection_error(openai.APITimeoutError))
    resp = client.post("/api/v1/agent/chat", json={"message": "你好"}, headers=auth)

    assert resp.status_code == 502
    assert "超时" in resp.json()["message"]


def test_connection_failure_points_at_the_endpoint(client_and_login):
    """A wrong LLM_BASE_URL usually shows up here, so name the variable."""
    client, auth = client_and_login(_connection_error(openai.APIConnectionError))
    resp = client.post("/api/v1/agent/chat", json={"message": "你好"}, headers=auth)

    assert resp.status_code == 502
    assert "LLM_BASE_URL" in resp.json()["message"]


def test_unknown_failure_keeps_the_generic_message(client_and_login):
    """Unrecognised errors must not claim to know the cause."""
    client, auth = client_and_login(RuntimeError("something unexpected"))
    resp = client.post("/api/v1/agent/chat", json={"message": "你好"}, headers=auth)

    assert resp.status_code == 502
    assert resp.json()["message"] == "AI 服务暂时不可用，请稍后重试"
