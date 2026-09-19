import json
import logging
import threading
import time
from .common import new_id
from .training import compute_mastery, STAGE_ORDER, STAGE_TITLES


class TrainingWorker:
    def __init__(self, database):
        self.database = database
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="training-worker")

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=20)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            delay = 0.5
            try:
                delay = self.tick()
            except Exception:
                logging.getLogger(__name__).exception("Training worker tick failed")
            self.wake.wait(delay)

    def tick(self):
        now = time.time()
        next_delay = 0.5
        with self.database.transaction() as db:
            rows = db.execute("SELECT * FROM attempts WHERE status IN ('queued','running') ORDER BY created_at LIMIT 100").fetchall()
            for row in rows:
                if now >= row["deadline_at"]:
                    db.execute("UPDATE attempts SET status='failed',error_json=? WHERE id=?", (json.dumps({"code": 50401, "message": "作答处理超时，请重新提交"}, ensure_ascii=False), row["id"]))
                    continue
                if row["status"] == "queued":
                    db.execute("UPDATE attempts SET status='running' WHERE id=?", (row["id"],))
                if now < row["ready_at"]:
                    next_delay = min(next_delay, max(0.001, row["ready_at"] - now))
                    continue
                self.grade(db, row)
            exports = db.execute("SELECT * FROM training_exports WHERE status IN ('queued','running') ORDER BY created_at LIMIT 20").fetchall()
            for row in exports:
                if now >= row["deadline_at"]:
                    db.execute("UPDATE training_exports SET status='failed',error_json=? WHERE id=?", (json.dumps({"code": 50401, "message": "导出超时，请重新提交"}, ensure_ascii=False), row["id"]))
                    continue
                if row["status"] == "queued":
                    db.execute("UPDATE training_exports SET status='running' WHERE id=?", (row["id"],))
                if now < row["ready_at"]:
                    next_delay = min(next_delay, max(0.001, row["ready_at"] - now))
                    continue
                self.export(db, row)
        return next_delay

    def export(self, db, row):
        from .pdf import render_training_pdf
        training = db.execute("SELECT * FROM trainings WHERE id=?", (row["training_id"],)).fetchone()
        exam = db.execute("SELECT course FROM exams WHERE id=?", (training["exam_id"],)).fetchone()
        include_answers, include_analysis = bool(row["include_answers"]), bool(row["include_analysis"])
        grouped = {}
        for question in db.execute("SELECT stage_type,payload_json,answer_json FROM training_questions WHERE training_id=? ORDER BY stage_type,position", (row["training_id"],)).fetchall():
            payload = json.loads(question["payload_json"])
            item = {"content": payload["content"], "options": payload.get("options", [])}
            if include_answers or include_analysis:
                answer = json.loads(question["answer_json"]) if question["answer_json"] else {}
                item["answer"], item["analysis"] = answer.get("answer"), answer.get("analysis")
            grouped.setdefault(question["stage_type"], []).append(item)
        groups = [(STAGE_TITLES[stage], grouped[stage]) for stage in STAGE_ORDER if grouped.get(stage)]
        file_id = new_id()
        path = self.database.data_dir / "uploads" / file_id
        try:
            render_training_pdf(path, training["title"], f"课程：{exam['course']}    目标掌握度：{training['target_mastery']}    当前掌握度：{training['current_mastery'] if training['current_mastery'] is not None else '尚未评估'}", groups, include_answers, include_analysis)
            # Name the columns: the files table gained sha256/purpose in the
            # question-bank migration, so a positional INSERT is no longer valid.
            db.execute(
                "INSERT INTO files(id,user_id,storage_key,original_name,mime_type,size,created_at) VALUES (?,?,?,?,?,?,?)",
                (file_id, row["user_id"], file_id, f"{training['title']}.pdf", "application/pdf", path.stat().st_size, time.time()),
            )
            db.execute("UPDATE training_exports SET status='succeeded',file_id=?,error_json=NULL WHERE id=?", (file_id, row["id"]))
        except Exception:
            logging.getLogger(__name__).exception("Training export failed for %s", row["id"])
            if path.exists(): path.unlink()
            db.execute("UPDATE training_exports SET status='failed',error_json=? WHERE id=?", (json.dumps({"code": 50001, "message": "导出失败，请稍后重试"}, ensure_ascii=False), row["id"]))

    def grade(self, db, row):
        training = db.execute("SELECT * FROM trainings WHERE id=?", (row["training_id"],)).fetchone()
        exam = db.execute("SELECT course FROM exams WHERE id=?", (training["exam_id"],)).fetchone()
        question = db.execute(
            "SELECT payload_json,answer_json FROM training_questions WHERE training_id=? AND question_id=?",
            (row["training_id"], row["question_id"]),
        ).fetchone()
        payload = json.loads(question["payload_json"])
        max_score = float(payload["score"])
        if row["file_ids_json"]:
            correct, analysis = True, "拍照作答已识别（示例数据，待接入真实判卷）。"
        else:
            answer = json.loads(question["answer_json"])
            correct = (row["answer_text"] or "").strip().lower() == answer["answer"].lower()
            analysis = answer["analysis"]
        score = max_score if correct else 0.0
        before = compute_mastery(db, row["user_id"], exam["course"], training["knowledge_point_id"])
        now = time.time()
        db.execute("INSERT OR IGNORE INTO mastery_evidence VALUES (?,?,?,?,?,?,?,?,?)", (new_id(), row["user_id"], exam["course"], training["knowledge_point_id"], row["id"], "attempt", score, max_score, now))
        after = compute_mastery(db, row["user_id"], exam["course"], training["knowledge_point_id"])
        result = {"score": score, "maxScore": max_score, "correct": correct, "analysis": analysis, "masteryBefore": before, "masteryAfter": after}
        db.execute("UPDATE attempts SET status='succeeded',result_json=?,error_json=NULL,mastery_before=?,mastery_after=? WHERE id=?", (json.dumps(result, ensure_ascii=False), before, after, row["id"]))
        db.execute("UPDATE trainings SET current_mastery=?,updated_at=? WHERE id=?", (after, now, row["training_id"]))
