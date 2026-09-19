"""Debug script: send a minimal request to DeepSeek to reproduce the 400 error.

Usage: .venv/Scripts/python debug_llm.py
Requires LLM_API_KEY env var or .env file.
"""
import json
import os
from dotenv import load_dotenv
load_dotenv()

import httpx

API_KEY = os.getenv("LLM_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

if not API_KEY:
    print("ERROR: LLM_API_KEY not set. Set it in .env or as env var.")
    exit(1)

print(f"BASE_URL: {BASE_URL}")
print(f"MODEL: {MODEL}")
print(f"API_KEY: {API_KEY[:8]}...{API_KEY[-4:]}")
print()

# ---- Test 1: Minimal request (no tools) ----
print("=" * 60)
print("TEST 1: Minimal request without tools")
payload1 = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one word."},
    ],
    "temperature": 0.3,
    "max_tokens": 50,
}
print(f"Payload: {json.dumps(payload1, ensure_ascii=False)[:200]}")
try:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload1,
        )
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Exception: {e}")

print()

# ---- Test 2: With tools ----
print("=" * 60)
print("TEST 2: With tools (function calling)")
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_study_summary",
            "description": "Get user study summary",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
payload2 = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Analyze my study situation."},
    ],
    "temperature": 0.3,
    "max_tokens": 2000,
    "tools": TOOLS,
    "tool_choice": "auto",
}
print(f"Payload keys: {list(payload2.keys())}")
try:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload2,
        )
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:800]}")
except Exception as e:
    print(f"Exception: {e}")

print()

# ---- Test 3: With tool_calls in history (simulates 2nd round) ----
print("=" * 60)
print("TEST 3: With tool_calls history (multi-round)")
payload3 = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Analyze my study situation."},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "get_study_summary",
                        "arguments": "{}",
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": '{"totalExams": 1, "totalGradings": 0}',
            "tool_call_id": "call_abc123",
        },
    ],
    "temperature": 0.3,
    "max_tokens": 2000,
    "tools": TOOLS,
    "tool_choice": "auto",
}
try:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload3,
        )
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:800]}")
except Exception as e:
    print(f"Exception: {e}")
