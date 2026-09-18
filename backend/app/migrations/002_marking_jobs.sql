CREATE TABLE marking_jobs (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id),
 exam_id TEXT NOT NULL REFERENCES exams(id),
 file_id TEXT NOT NULL REFERENCES files(id),
 request_key TEXT NOT NULL,
 fingerprint TEXT NOT NULL,
 provider_job_id TEXT,
 status TEXT NOT NULL,
 image_json TEXT NOT NULL,
 result_json TEXT,
 raw_json TEXT,
 error_json TEXT,
 request_id TEXT,
 created_at REAL NOT NULL,
 last_poll REAL NOT NULL DEFAULT 0,
 UNIQUE(user_id,request_key)
);
