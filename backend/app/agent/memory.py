"""Memory management for the FinalBoost Agent.

Implements:
- Sliding window for recent conversation history
- Long-term memory storage and retrieval
- Token budget management

Works with both SQLite and MySQL via the existing db.transaction() interface.
"""
from __future__ import annotations
import json
import logging
import time
import uuid
from typing import Optional
from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
)

logger = logging.getLogger(__name__)

MAX_TURNS = 50
MAX_TOKENS = 24000  # Approximate token budget


class MemoryManager:
    """Manages conversation memory with sliding window and long-term storage."""

    def __init__(self, db):
        self.db = db

    def get_recent_messages(self, session_id: str, limit: int = MAX_TURNS) -> list[BaseMessage]:
        """Get recent messages from database for a session.

        Returns messages in chronological order (oldest first) as LangChain message objects.
        """
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT role, content, tool_calls, tool_call_id, name "
                "FROM agent_messages "
                "WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()

        messages = []
        for row in reversed(rows):
            role = row["role"]
            if role == "user":
                messages.append(HumanMessage(content=row["content"] or ""))
            elif role == "assistant":
                # Stored calls are UI traces on the final answer, not pending model calls.
                if row["content"]:
                    messages.append(AIMessage(content=row["content"]))
            elif role == "tool":
                continue
            elif role == "system":
                messages.append(SystemMessage(content=row["content"] or ""))

        # Remove orphan ToolMessages that have no preceding AIMessage with matching tool_calls
        return self._clean_orphan_tool_messages(messages)

    @staticmethod
    def _clean_orphan_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
        """Remove ToolMessages that have no preceding AIMessage with matching tool_calls."""
        # Collect all tool_call_ids declared by AIMessages
        valid_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    valid_ids.add(tc.get("id", ""))

        # Filter out ToolMessages whose tool_call_id is not in valid_ids
        cleaned = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                if msg.tool_call_id and msg.tool_call_id in valid_ids:
                    cleaned.append(msg)
                else:
                    logger.debug("Dropping orphan ToolMessage tool_call_id=%s", msg.tool_call_id)
            else:
                cleaned.append(msg)
        return cleaned

    def get_long_term_memories(self, user_id: str, query: str = "") -> list[str]:
        """Retrieve relevant long-term memories for a user.

        Returns list of memory strings that might be relevant to the query.
        """
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT memory_key, memory_value FROM agent_long_term_memory "
                "WHERE user_id=? AND active=1 "
                "AND (expires_at IS NULL OR expires_at > ?) "
                "ORDER BY updated_at DESC LIMIT 20",
                (user_id, time.time()),
            ).fetchall()

        if not rows:
            return []

        memories = []
        query_lower = query.lower() if query else ""

        for row in rows:
            memory_str = f"{row['memory_key']}={row['memory_value']}"
            if not query_lower:
                memories.append(memory_str)
            else:
                query_words = query_lower.split()
                memory_lower = memory_str.lower()
                if any(word in memory_lower for word in query_words):
                    memories.append(memory_str)

        return memories[:8]

    def save_long_term_memory(
        self, user_id: str, key: str, value: str,
        expires_in_days: Optional[int] = None
    ) -> None:
        """Save or update a long-term memory entry."""
        now = time.time()
        expires_at = None
        if expires_in_days:
            expires_at = now + expires_in_days * 86400

        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM agent_long_term_memory "
                "WHERE user_id=? AND memory_key=?",
                (user_id, key),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE agent_long_term_memory "
                    "SET memory_value=?, updated_at=? "
                    "WHERE id=?",
                    (value, now, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO agent_long_term_memory "
                    "(user_id, memory_key, memory_value, active, expires_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, 1, ?, ?, ?)",
                    (user_id, key, value, expires_at, now, now),
                )

    def estimate_tokens(self, messages: list) -> int:
        """Rough token estimate for a list of messages.

        Uses character count / 2 as approximation for mixed Chinese/English.
        """
        total_chars = 0
        for msg in messages:
            if hasattr(msg, 'content') and msg.content:
                total_chars += len(str(msg.content))
        return max(1, total_chars // 2)

    def trim_to_budget(self, messages: list, max_tokens: int = MAX_TOKENS) -> list:
        """Trim messages to fit within token budget.

        Always keeps the most recent messages, removes oldest first.
        Preserves system message at index 0 if present.
        """
        if not messages:
            return messages

        system_msg = None
        other_msgs = list(messages)
        if isinstance(messages[0], SystemMessage):
            system_msg = messages[0]
            other_msgs = messages[1:]

        while self.estimate_tokens(other_msgs) > max_tokens and len(other_msgs) > 1:
            other_msgs.pop(0)

        if system_msg:
            return [system_msg] + other_msgs
        return other_msgs

    def save_message(self, session_id: str, role: str, content: str,
                     tool_calls: list = None, tool_call_id: str = None,
                     name: str = None) -> None:
        """Save a message to the database."""
        now = time.time()
        msg_id = uuid.uuid4().hex[:16]

        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO agent_messages "
                "(id, session_id, role, content, tool_calls, tool_call_id, name, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    msg_id,
                    session_id,
                    role,
                    content,
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                    tool_call_id,
                    name,
                    now,
                ),
            )

    def update_session_timestamp(self, session_id: str) -> None:
        """Update the session's updated_at timestamp."""
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE agent_sessions SET updated_at=? WHERE id=?",
                (time.time(), session_id),
            )
