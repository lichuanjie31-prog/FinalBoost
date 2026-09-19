"""Test agent chat API — verify no duplicate messages returned from backend."""
import json
from fastapi.testclient import TestClient
from app.main import create_app

HEADERS = {"X-Requested-With": "FinalBoost", "Origin": "http://127.0.0.1:5173"}
PASSWORD = "Test-password-12345"


def client_for(tmp_path, **kwargs):
    return TestClient(create_app(data_dir=tmp_path, grading_mode="mock", **kwargs))


def register(client, name="student_one"):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": name, "password": PASSWORD},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def bearer(data):
    return {"Authorization": "Bearer " + data["accessToken"]}


def test_agent_chat_returns_single_assistant_message(tmp_path):
    """BUG REPRO: verify backend returns exactly 1 assistant message per turn.

    If the backend returns duplicates, the frontend bug is server-side.
    If the backend returns correctly, the bug is the frontend useEffect
    loading messages that were just added locally.
    """
    with client_for(tmp_path) as c:
        auth = register(c)
        headers = {**HEADERS, **bearer(auth)}

        # Send first message (new session)
        r1 = c.post(
            "/api/v1/agent/chat",
            json={"message": "帮我分析一下学习情况"},
            headers=headers,
        )
        assert r1.status_code == 200, r1.text
        d1 = r1.json()["data"]
        session_id = d1["sessionId"]

        # Verify response shape — exactly 1 message content
        assert d1["message"], "Expected assistant message content"
        print(f"[TEST] First response: sessionId={session_id}, message={d1['message'][:80]}...")
        print(f"[TEST] Tool calls: {len(d1['toolCalls'])}")

        # Now fetch messages from the session endpoint
        r2 = c.get(
            f"/api/v1/agent/sessions/{session_id}/messages",
            headers=headers,
        )
        assert r2.status_code == 200
        messages = r2.json()["data"]
        print(f"\n[TEST] Messages in session after 1st turn: {len(messages)}")
        for m in messages:
            print(f"  - role={m['role']}, id={m['id']}, content={str(m.get('content',''))[:60]}")

        # Count assistant messages
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        user_msgs = [m for m in messages if m["role"] == "user"]

        print(f"\n[TEST] User messages: {len(user_msgs)}")
        print(f"[TEST] Assistant messages: {len(assistant_msgs)}")

        assert len(user_msgs) == 1, f"Expected 1 user message, got {len(user_msgs)}"
        assert len(assistant_msgs) == 1, f"Expected 1 assistant message, got {len(assistant_msgs)} — DUPLICATE BUG!"

        # Send second message in the same session
        r3 = c.post(
            "/api/v1/agent/chat",
            json={"message": "我有哪些薄弱知识点", "sessionId": session_id},
            headers=headers,
        )
        assert r3.status_code == 200, r3.text

        # Fetch messages again
        r4 = c.get(
            f"/api/v1/agent/sessions/{session_id}/messages",
            headers=headers,
        )
        messages2 = r4.json()["data"]
        assistant_msgs2 = [m for m in messages2 if m["role"] == "assistant"]
        user_msgs2 = [m for m in messages2 if m["role"] == "user"]

        print(f"\n[TEST] After 2nd turn:")
        print(f"  User messages: {len(user_msgs2)}")
        print(f"  Assistant messages: {len(assistant_msgs2)}")

        assert len(user_msgs2) == 2, f"Expected 2 user messages, got {len(user_msgs2)}"
        assert len(assistant_msgs2) == 2, f"Expected 2 assistant messages, got {len(assistant_msgs2)}"

        print("\n[TEST] PASS: Backend returns correct message counts - bug is FRONTEND-side")


def test_agent_chat_session_id_consistency(tmp_path):
    """Verify the same session_id is returned and persisted correctly."""
    with client_for(tmp_path) as c:
        auth = register(c)
        headers = {**HEADERS, **bearer(auth)}

        # First message — creates session
        r1 = c.post("/api/v1/agent/chat", json={"message": "你好"}, headers=headers)
        sid1 = r1.json()["data"]["sessionId"]

        # Second message — reuses session
        r2 = c.post(
            "/api/v1/agent/chat",
            json={"message": "你好", "sessionId": sid1},
            headers=headers,
        )
        sid2 = r2.json()["data"]["sessionId"]

        assert sid1 == sid2, "Session ID should be consistent across turns"

        # Verify sessions list
        r3 = c.get("/api/v1/agent/sessions", headers=headers)
        sessions = r3.json()["data"]
        assert len(sessions) == 1, "Should have exactly 1 session"
        print("[TEST] PASS: Session ID consistency verified")
