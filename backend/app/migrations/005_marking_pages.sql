-- Per-page marking jobs: explicit page order plus a separate slot for the query
-- RequestId, so the submit RequestId is no longer overwritten when polling.
ALTER TABLE marking_jobs ADD COLUMN page_index INTEGER NOT NULL DEFAULT 0;
ALTER TABLE marking_jobs ADD COLUMN query_request_id TEXT;
