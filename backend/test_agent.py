"""Quick test script for the LangChain Agent."""
import httpx
import json
import sys

# Fix encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://localhost:8000"

def test():
    # Register a test user (password must be 10+ chars)
    r = httpx.post(f"{BASE}/api/v1/auth/register",
                   json={"username": "testuser", "password": "test123456789"},
                   headers={"X-Requested-With": "FinalBoost"})
    if r.status_code == 201:
        token = r.json()["data"]["accessToken"]
        print("[OK] Registered & logged in")
    elif r.status_code == 409:
        # Already registered, login
        r = httpx.post(f"{BASE}/api/v1/auth/login",
                       json={"username": "testuser", "password": "test123456789"},
                       headers={"X-Requested-With": "FinalBoost"})
        token = r.json()["data"]["accessToken"]
        print("[OK] Logged in")
    else:
        print(f"[FAIL] Auth failed: {r.text}")
        return

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Test health
    r = httpx.get(f"{BASE}/api/v1/health")
    print(f"\n=== Health ===\n{json.dumps(r.json(), indent=2, ensure_ascii=False)}")

    # Test agent chat (mock mode)
    r = httpx.post(f"{BASE}/api/v1/agent/chat",
                   json={"message": "你好，帮我分析一下学习情况"},
                   headers=headers)
    data = r.json()
    print(f"\n=== Agent Chat ===")
    print(f"Status: {r.status_code}")
    print(f"Session: {data.get('data', {}).get('sessionId', 'N/A')}")
    print(f"Reply: {data.get('data', {}).get('message', 'N/A')[:200]}")
    print(f"Tools: {len(data.get('data', {}).get('toolCalls', []))} calls")

    # Test agent chat with tool keywords
    r = httpx.post(f"{BASE}/api/v1/agent/chat",
                   json={"message": "我有哪些薄弱知识点？"},
                   headers=headers)
    data = r.json()
    print(f"\n=== Agent Chat (weak points) ===")
    print(f"Reply: {data.get('data', {}).get('message', 'N/A')[:200]}")
    print(f"Tools: {[tc['name'] for tc in data.get('data', {}).get('toolCalls', [])]}")

    # List sessions
    r = httpx.get(f"{BASE}/api/v1/agent/sessions", headers=headers)
    resp = r.json()
    sessions = resp.get("data") or []
    print(f"\n=== Sessions ===\nTotal: {len(sessions)}")
    for s in sessions[:3]:
        print(f"  - {s.get('title', 'N/A')[:30]} ({s.get('sessionId', 'N/A')[:8]}...)")

    print("\n[DONE] All tests passed!")


if __name__ == "__main__":
    test()
