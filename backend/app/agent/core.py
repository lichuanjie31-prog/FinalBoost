"""Agent core loop: receive message → call LLM → handle tool calls → return response.

Supports multi-round tool calling (max 3 rounds to prevent infinite loops).
"""
from __future__ import annotations
import json
import logging
import time
import uuid
from .context import build_messages
from .tools import LLMClient, execute_tool, TOOL_DEFINITIONS

MAX_TOOL_ROUNDS = 3
logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def run_agent_turn(db, user_id: str, session_id: str, user_message: str, llm: LLMClient,
                    exam_id: str | None = None, grading_id: str | None = None) -> dict:
    """Execute one agent turn: user message → (tool calls)* → assistant reply.

    Returns dict with keys: content, tool_calls (list of {id, name, arguments, result}).
    """
    # Build initial context
    messages = build_messages(db, user_id, session_id, user_message, exam_id, grading_id)

    all_tool_calls = []  # track all tool calls for this turn
    last_content = ""
    last_tool_calls_json = None

    for round_num in range(MAX_TOOL_ROUNDS):
        # Call LLM
        logger.info("Agent round %d: %d messages, %d tools available",
                     round_num + 1, len(messages), len(TOOL_DEFINITIONS))
        try:
            response = llm.chat_completion(messages, tools=TOOL_DEFINITIONS)
        except Exception:
            logger.exception("LLM call failed at round %d", round_num + 1)
            raise

        choice = response["choices"][0]
        assistant_msg = choice["message"]
        finish_reason = choice.get("finish_reason", "")

        # Extract content and tool calls
        last_content = assistant_msg.get("content") or ""
        last_tool_calls_json = assistant_msg.get("tool_calls")

        if not last_tool_calls_json or finish_reason == "stop":
            # No tool calls — we're done
            break

        # Process tool calls
        # Ensure each tool call has required "type" field for API compatibility
        for tc in last_tool_calls_json:
            tc.setdefault("type", "function")

        messages.append(assistant_msg)  # add assistant message with tool_calls to context

        for tc in last_tool_calls_json:
            tc_id = tc.get("id", _new_id())
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            fn_args_str = fn.get("arguments", "{}")

            try:
                fn_args = json.loads(fn_args_str)
            except json.JSONDecodeError:
                fn_args = {}

            logger.info("Executing tool: %s(%s)", fn_name, json.dumps(fn_args, ensure_ascii=False))

            # Execute the tool
            result = execute_tool(db, user_id, llm, fn_name, fn_args)
            logger.info("Tool %s result: %s...", fn_name, result[:200])

            # Track for response
            all_tool_calls.append({
                "id": tc_id,
                "name": fn_name,
                "arguments": fn_args,
                "result": result,
            })

            # Add tool result to messages for next LLM round
            messages.append({
                "role": "tool",
                "content": result,
                "tool_call_id": tc_id,
                "name": fn_name,
            })

    return {
        "content": last_content,
        "tool_calls": all_tool_calls,
        "tool_calls_json": last_tool_calls_json,
    }


def save_turn(db, session_id: str, user_message: str, result: dict) -> None:
    """Persist the user message and assistant response to the database."""
    now = time.time()

    # Save user message
    db.execute(
        "INSERT INTO agent_messages(id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (_new_id(), session_id, "user", user_message, now - 1),
    )

    # Save tool call messages (if any)
    if result["tool_calls"]:
        for tc in result["tool_calls"]:
            # Tool result message
            db.execute(
                "INSERT INTO agent_messages(id, session_id, role, content, tool_call_id, name, created_at) VALUES (?,?,?,?,?,?,?)",
                (_new_id(), session_id, "tool", tc["result"], tc["id"], tc["name"], now),
            )

    # Save assistant reply
    db.execute(
        "INSERT INTO agent_messages(id, session_id, role, content, tool_calls, created_at) VALUES (?,?,?,?,?,?)",
        (
            _new_id(),
            session_id,
            "assistant",
            result["content"],
            json.dumps(result["tool_calls_json"], ensure_ascii=False) if result["tool_calls_json"] else None,
            now + 1,
        ),
    )

    # Update session timestamp
    db.execute(
        "UPDATE agent_sessions SET updated_at=? WHERE id=?",
        (now, session_id),
    )