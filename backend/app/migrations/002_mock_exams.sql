-- 最终模拟（mock exam）：从题库抽题组一套卷 → 学生作答 → 判卷
-- 对应 API 文档 v1.0 第 15 节

CREATE TABLE mock_exams (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  exam_id TEXT NOT NULL REFERENCES exams(id),
  status TEXT NOT NULL CHECK(status IN ('ready','submitted','graded')),
  -- 题目（含标准答案），结构：[{ questionId, prompt, options?, maxScore, knowledgePointIds, knowledgePoints, correctAnswer }]
  questions_json TEXT NOT NULL,
  -- 学生作答，结构：[{ questionId, answer, answeredAt }]
  answers_json TEXT NOT NULL DEFAULT '[]',
  -- 来源：mock 表示内置示例题库，paper 表示从试卷题库抽（保留扩展位）
  source TEXT NOT NULL DEFAULT 'mock',
  created_at REAL NOT NULL,
  submitted_at REAL,
  graded_at REAL
);
CREATE INDEX mock_exams_owner ON mock_exams(user_id,exam_id,id);
ALTER TABLE grading_jobs ADD COLUMN mock_exam_id TEXT REFERENCES mock_exams(id);