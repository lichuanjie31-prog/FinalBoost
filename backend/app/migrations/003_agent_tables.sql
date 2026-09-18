-- Agent: conversation sessions
CREATE TABLE IF NOT EXISTS agent_sessions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    title       TEXT NOT NULL DEFAULT '新对话',
    course      TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS agent_sessions_owner ON agent_sessions(user_id, updated_at);

-- Agent: messages within a session
CREATE TABLE IF NOT EXISTS agent_messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content     TEXT,
    tool_calls  TEXT,   -- JSON array of tool call objects (when role=assistant)
    tool_call_id TEXT,  -- which tool call this result responds to (when role=tool)
    name        TEXT,   -- tool name (when role=tool)
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS agent_messages_session ON agent_messages(session_id, created_at);