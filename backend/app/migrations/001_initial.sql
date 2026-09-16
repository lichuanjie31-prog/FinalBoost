CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE refresh_tokens (digest TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE access_tokens (digest TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), expires_at REAL NOT NULL);
CREATE TABLE exams (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), course TEXT NOT NULL,
 exam_date TEXT NOT NULL, target_score REAL NOT NULL, max_score REAL NOT NULL,
 stage TEXT NOT NULL DEFAULT 'diagnosis', created_at REAL NOT NULL,
 CHECK(target_score>0 AND max_score>0 AND target_score<=max_score)
);
CREATE INDEX exams_owner ON exams(user_id,id);
CREATE TABLE files (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), storage_key TEXT NOT NULL UNIQUE,
 original_name TEXT NOT NULL, mime_type TEXT NOT NULL, size INTEGER NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE grading_jobs (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), exam_id TEXT NOT NULL REFERENCES exams(id),
 status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
 scenario TEXT NOT NULL, created_at REAL NOT NULL, started_at REAL, ready_at REAL NOT NULL, deadline_at REAL NOT NULL,
 result_json TEXT, error_json TEXT, source TEXT NOT NULL DEFAULT 'mock'
);
CREATE INDEX grading_owner_exam ON grading_jobs(user_id,exam_id,id);
CREATE TABLE grading_files (
 grading_id TEXT NOT NULL REFERENCES grading_jobs(id), file_id TEXT NOT NULL REFERENCES files(id),
 page_index INTEGER NOT NULL, PRIMARY KEY(grading_id,page_index), UNIQUE(grading_id,file_id)
);
CREATE TABLE diagnoses (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), exam_id TEXT NOT NULL REFERENCES exams(id),
 grading_id TEXT NOT NULL UNIQUE REFERENCES grading_jobs(id), data_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE idempotency_records (
 user_id TEXT NOT NULL REFERENCES users(id), method TEXT NOT NULL, path TEXT NOT NULL, key TEXT NOT NULL,
 request_hash TEXT NOT NULL, response_status INTEGER NOT NULL, response_json TEXT NOT NULL, expires_at REAL NOT NULL,
 PRIMARY KEY(user_id,method,path,key)
);
