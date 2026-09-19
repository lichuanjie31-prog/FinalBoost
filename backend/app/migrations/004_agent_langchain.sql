-- Agent tables for LangChain/LangGraph integration
-- Compatible with both SQLite and MySQL

-- Long-term memory table
CREATE TABLE IF NOT EXISTS agent_long_term_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    memory_value TEXT,
    active INTEGER DEFAULT 1,
    expires_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_user ON agent_long_term_memory(user_id, active);
CREATE INDEX IF NOT EXISTS idx_memory_key ON agent_long_term_memory(user_id, memory_key);

-- Knowledge documents metadata
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    filename TEXT,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'indexed',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_user ON knowledge_documents(user_id, created_at);
