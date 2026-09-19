CREATE TABLE trainings (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), exam_id TEXT NOT NULL REFERENCES exams(id),
 knowledge_point_id TEXT NOT NULL, knowledge_point TEXT NOT NULL, title TEXT NOT NULL,
 current_mastery REAL, target_mastery REAL NOT NULL DEFAULT 80, estimated_score_gain REAL,
 status TEXT NOT NULL DEFAULT 'active', created_at REAL NOT NULL, updated_at REAL NOT NULL,
 CHECK(target_mastery>0 AND target_mastery<=100),
 CHECK(status IN ('active','completed'))
);
CREATE INDEX trainings_owner ON trainings(user_id,exam_id,id);
CREATE TABLE training_stages (
 training_id TEXT NOT NULL REFERENCES trainings(id), stage_type TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'locked', content_json TEXT,
 PRIMARY KEY(training_id,stage_type),
 CHECK(stage_type IN ('method','guided','easy','medium','quiz')),
 CHECK(status IN ('locked','unlocked','completed'))
);
CREATE TABLE training_questions (
 training_id TEXT NOT NULL REFERENCES trainings(id), stage_type TEXT NOT NULL, position INTEGER NOT NULL,
 question_id TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'real_exam', payload_json TEXT NOT NULL,
 PRIMARY KEY(training_id,stage_type,position),
 CHECK(position>=0),
 CHECK(stage_type IN ('method','guided','easy','medium','quiz'))
);
CREATE TABLE attempts (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), training_id TEXT NOT NULL REFERENCES trainings(id),
 question_id TEXT NOT NULL, stage_type TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
 answer_text TEXT, file_ids_json TEXT, result_json TEXT, error_json TEXT,
 mastery_before REAL, mastery_after REAL, duration_seconds INTEGER NOT NULL,
 created_at REAL NOT NULL, ready_at REAL NOT NULL, deadline_at REAL NOT NULL,
 CHECK(duration_seconds>=0),
 CHECK((answer_text IS NOT NULL)<>(file_ids_json IS NOT NULL)),
 CHECK(stage_type IN ('method','guided','easy','medium','quiz'))
);
CREATE INDEX attempts_owner_training ON attempts(user_id,training_id,id);
CREATE TABLE quizzes (
 id TEXT PRIMARY KEY, training_id TEXT NOT NULL REFERENCES trainings(id),
 question TEXT NOT NULL, type TEXT NOT NULL, answer_text TEXT,
 score REAL, concept_correct INTEGER, missing_points_json TEXT, mastery_after REAL, passed INTEGER,
 created_at REAL NOT NULL, answered_at REAL
);
CREATE INDEX quizzes_training ON quizzes(training_id,id);
CREATE TABLE mastery_evidence (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), course TEXT NOT NULL,
 knowledge_point_id TEXT NOT NULL, evidence_id TEXT NOT NULL, evidence_type TEXT NOT NULL,
 score REAL, max_score REAL, created_at REAL NOT NULL,
 UNIQUE(evidence_id),
 CHECK(evidence_type IN ('grading','attempt','quiz'))
);
CREATE INDEX mastery_evidence_owner ON mastery_evidence(user_id,course,knowledge_point_id);
