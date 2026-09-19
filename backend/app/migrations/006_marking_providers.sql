-- Multi-provider marking: record which provider produced each job, along with the
-- model and token accounting needed to reason about cost.
--
-- Every pre-existing row was produced by the Tencent provider, so 'tencent' is the
-- correct default for old data and those records stay readable unchanged.
-- `request_id` already carries the provider request id (submit-time for async
-- providers, the single call for synchronous ones); the poll id lives in
-- `query_request_id`.
ALTER TABLE marking_jobs ADD COLUMN provider TEXT NOT NULL DEFAULT 'tencent';
ALTER TABLE marking_jobs ADD COLUMN model TEXT;
ALTER TABLE marking_jobs ADD COLUMN usage_json TEXT;
ALTER TABLE marking_jobs ADD COLUMN latency_ms REAL;
