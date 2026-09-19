CREATE TABLE training_exports (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), training_id TEXT NOT NULL REFERENCES trainings(id),
 status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
 include_answers INTEGER NOT NULL DEFAULT 0, include_analysis INTEGER NOT NULL DEFAULT 0,
 file_id TEXT, error_json TEXT, created_at REAL NOT NULL, ready_at REAL NOT NULL, deadline_at REAL NOT NULL
);
CREATE INDEX training_exports_owner ON training_exports(user_id,training_id,id);
