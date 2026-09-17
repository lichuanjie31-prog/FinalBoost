import json
import time
from fastapi import APIRouter, Depends, Request, Query
from .auth import current_user
from .common import envelope, fail, new_id
from .idempotency import execute
from .schemas import (
    Envelope, Page, TrainingIn, TrainingOut, TrainingStage, StageOut, StageCompleteIn,
    StageCompleteOut, QuestionOut, AttemptIn, AttemptAccepted, AttemptOut,
    QuizOut, QuizAnswerIn, QuizAnswerOut, ExportIn, ExportAccepted, ExportOut,
)

router = APIRouter(prefix="/api/v1", tags=["training"])

STAGE_ORDER = ["method", "guided", "easy", "medium", "quiz"]
STAGE_TITLES = {
    "method": "题型速记",
    "guided": "AI 带做",
    "easy": "简单真题",
    "medium": "中等真题",
    "quiz": "掌握度检测",
}
QUESTION_STAGES = {"guided": (2, 2), "easy": (3, 1), "medium": (2, 3)}

def owned(db, table, rid, user_id):
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
    if row is None: fail(404, "记录不存在")
    if row["user_id"] != user_id: fail(403, "无权访问这条记录")
    return row

def knowledge_point_name(db, exam_id, kp_id):
    for row in db.execute("SELECT data_json FROM diagnoses WHERE exam_id=? ORDER BY created_at DESC", (exam_id,)).fetchall():
        for item in json.loads(row["data_json"]).get("outline", []):
            if item.get("knowledgePointId") == kp_id: return item.get("knowledgePoint")
    return kp_id

def compute_mastery(db, user_id, course, kp_id):
    rows = db.execute(
        "SELECT score,max_score,evidence_type FROM mastery_evidence WHERE user_id=? AND course=? AND knowledge_point_id=? ORDER BY created_at DESC",
        (user_id, course, kp_id),
    ).fetchall()
    if not rows: return None
    recent = rows[:20]
    total_max = sum(r["max_score"] for r in recent if r["max_score"])
    total_score = sum(r["score"] for r in recent if r["score"] is not None and r["max_score"])
    factors = {}
    if total_max > 0: factors["questionAccuracy"] = total_score / total_max * 100
    quiz_rows = [r for r in rows if r["evidence_type"] == "quiz"]
    if quiz_rows: factors["aiQuizScore"] = quiz_rows[0]["score"]
    last5 = rows[:5]
    if len(last5) >= 3:
        rates = [r["score"] / r["max_score"] * 100 for r in last5 if r["score"] is not None and r["max_score"]]
        if rates: factors["stability"] = min(rates)
    weights = {"questionAccuracy": 0.60, "aiQuizScore": 0.25, "stability": 0.15}
    total_weight = sum(weights[k] for k in factors)
    if total_weight == 0: return None
    return round(sum(factors[k] * weights[k] for k in factors) / total_weight, 1)

def seed_question(course, kp_id, kp_name, stage_type, index, difficulty, score):
    return {
        "questionId": f"{stage_type}_{index + 1}",
        "course": course,
        "year": None,
        "paperId": None,
        "paper": None,
        "content": f"关于「{kp_name}」的{STAGE_TITLES[stage_type]}练习 {index + 1}（示例题，待接入真题库）",
        "imageFileIds": [],
        "options": [
            {"key": "A", "text": "选项 A"},
            {"key": "B", "text": "选项 B"},
            {"key": "C", "text": "选项 C"},
            {"key": "D", "text": "选项 D"},
        ],
        "knowledgePointIds": [kp_id],
        "difficulty": difficulty,
        "score": score,
        "sourceType": "ai_variant",
    }

def stage_rows(db, training_id):
    return {r["stage_type"]: r for r in db.execute("SELECT * FROM training_stages WHERE training_id=?", (training_id,)).fetchall()}

def training_out(db, row):
    stages = [{"type": s, "title": STAGE_TITLES[s], "status": stage_rows(db, row["id"])[s]["status"]} for s in STAGE_ORDER]
    return {
        "trainingId": row["id"], "title": row["title"], "currentMastery": row["current_mastery"],
        "targetMastery": row["target_mastery"], "estimatedScoreGain": row["estimated_score_gain"], "stages": stages,
    }

def stage_out(db, training_id, stage_type):
    stage = db.execute("SELECT * FROM training_stages WHERE training_id=? AND stage_type=?", (training_id, stage_type)).fetchone()
    if stage is None: fail(404, "阶段不存在")
    if stage["status"] == "locked": fail(409, "该阶段尚未开放")
    content = json.loads(stage["content_json"]).get("content") if stage["content_json"] else None
    questions = [json.loads(r["payload_json"]) for r in db.execute(
        "SELECT payload_json FROM training_questions WHERE training_id=? AND stage_type=? ORDER BY position", (training_id, stage_type)
    ).fetchall()]
    return {"type": stage_type, "status": stage["status"], "content": content, "questions": questions}

@router.post("/trainings", response_model=Envelope[TrainingOut], status_code=201)
def create_training(body: TrainingIn, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            exam = owned(db, "exams", body.examId, user["id"])
            name = knowledge_point_name(db, body.examId, body.knowledgePointId)
            mastery = compute_mastery(db, user["id"], exam["course"], body.knowledgePointId)
            gain = round(max(0.0, body.targetMastery - mastery) / 8, 1) if mastery is not None else None
            rid, now = new_id(), time.time()
            db.execute(
                "INSERT INTO trainings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, user["id"], body.examId, body.knowledgePointId, name, f"{name} 专项突破",
                 mastery, body.targetMastery, gain, "active", now, now),
            )
            for stage_type in STAGE_ORDER:
                status = "unlocked" if stage_type == "method" else "locked"
                content = json.dumps({"content": f"「{name}」的题型速记与解题方法要点。"}, ensure_ascii=False) if stage_type == "method" else None
                db.execute("INSERT INTO training_stages VALUES (?,?,?,?)", (rid, stage_type, status, content))
            for stage_type, (count, difficulty) in QUESTION_STAGES.items():
                db.executemany("INSERT INTO training_questions(training_id,stage_type,position,question_id,source_type,payload_json,answer_json) VALUES (?,?,?,?,?,?,?)", [
                    (rid, stage_type, i, f"{stage_type}_{i + 1}", "ai_variant",
                     json.dumps(seed_question(exam["course"], body.knowledgePointId, name, stage_type, i, difficulty, 8), ensure_ascii=False),
                     json.dumps({"answer": "A", "analysis": f"「{name}」{STAGE_TITLES[stage_type]}练习 {i + 1} 的正确答案为 A（示例解析）。"}, ensure_ascii=False))
                    for i in range(count)
                ])
            return training_out(db, db.execute("SELECT * FROM trainings WHERE id=?", (rid,)).fetchone())
        return execute(db, user["id"], request, body.model_dump(), 201, create)

@router.get("/trainings", response_model=Envelope[Page[TrainingOut]])
def list_trainings(request: Request, cursor: str | None = None, limit: int = Query(20, ge=1, le=100), user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        rows = db.execute("SELECT * FROM trainings WHERE user_id=? AND id>? ORDER BY id LIMIT ?", (user["id"], cursor or "", limit + 1)).fetchall()
        items = [training_out(db, row) for row in rows[:limit]]
        next_cursor = rows[limit - 1]["id"] if len(rows) > limit else None
    return envelope({"items": items, "nextCursor": next_cursor})

@router.get("/trainings/{training_id}", response_model=Envelope[TrainingOut])
def get_training(training_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        return envelope(training_out(db, owned(db, "trainings", training_id, user["id"])))

@router.get("/trainings/{training_id}/stages/{stage_type}", response_model=Envelope[StageOut])
def get_stage(training_id: str, stage_type: str, request: Request, user=Depends(current_user)):
    if stage_type not in STAGE_ORDER: fail(404, "阶段不存在")
    with request.app.state.db.transaction() as db:
        owned(db, "trainings", training_id, user["id"])
        return envelope(stage_out(db, training_id, stage_type))

@router.post("/trainings/{training_id}/stages/{stage_type}/complete", response_model=Envelope[StageCompleteOut])
def complete_stage(training_id: str, stage_type: str, body: StageCompleteIn, request: Request, user=Depends(current_user)):
    if stage_type not in STAGE_ORDER: fail(404, "阶段不存在")
    with request.app.state.db.transaction() as db:
        def create():
            training = owned(db, "trainings", training_id, user["id"])
            stage = db.execute("SELECT * FROM training_stages WHERE training_id=? AND stage_type=?", (training_id, stage_type)).fetchone()
            if stage["status"] == "locked": fail(409, "该阶段尚未开放")
            if stage["status"] == "completed": fail(409, "该阶段已完成")
            if stage_type == "quiz": fail(409, "掌握度检测由检测结果自动完成")
            if stage_type in QUESTION_STAGES:
                missing = db.execute(
                    "SELECT COUNT(*) FROM training_questions q WHERE q.training_id=? AND q.stage_type=? AND NOT EXISTS ("
                    "SELECT 1 FROM attempts a WHERE a.training_id=q.training_id AND a.question_id=q.question_id AND a.status='succeeded')",
                    (training_id, stage_type),
                ).fetchone()[0]
                if missing: fail(409, "请先完成本阶段全部题目")
            db.execute("UPDATE training_stages SET status='completed' WHERE training_id=? AND stage_type=?", (training_id, stage_type))
            index = STAGE_ORDER.index(stage_type)
            next_type = STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None
            if next_type:
                db.execute("UPDATE training_stages SET status='unlocked' WHERE training_id=? AND stage_type=?", (training_id, next_type))
            db.execute("UPDATE trainings SET updated_at=? WHERE id=?", (time.time(), training_id))
            return {"type": stage_type, "status": "completed", "nextStageType": next_type}
        return execute(db, user["id"], request, body.model_dump(), 200, create)

def attempt_out(row):
    return {
        "attemptId": row["id"],
        "status": row["status"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": json.loads(row["error_json"]) if row["error_json"] else None,
    }

@router.post("/trainings/{training_id}/attempts", response_model=Envelope[AttemptAccepted], status_code=202)
def submit_attempt(training_id: str, body: AttemptIn, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            owned(db, "trainings", training_id, user["id"])
            question = db.execute("SELECT * FROM training_questions WHERE training_id=? AND question_id=?", (training_id, body.questionId)).fetchone()
            if question is None: fail(404, "题目不存在")
            stage = db.execute("SELECT status FROM training_stages WHERE training_id=? AND stage_type=?", (training_id, question["stage_type"])).fetchone()
            if stage["status"] != "unlocked": fail(409, "该阶段尚未开放")
            if body.fileIds:
                for fid in body.fileIds: owned(db, "files", fid, user["id"])
            settings = request.app.state.settings
            rid, now = new_id(), time.time()
            db.execute(
                "INSERT INTO attempts(id,user_id,training_id,question_id,stage_type,status,answer_text,file_ids_json,duration_seconds,created_at,ready_at,deadline_at) "
                "VALUES (?,?,?,?,?,'queued',?,?,?,?,?,?)",
                (rid, user["id"], training_id, body.questionId, question["stage_type"], body.answer,
                 json.dumps(body.fileIds) if body.fileIds else None, body.durationSeconds, now, now, now + settings.job_timeout),
            )
            return {"attemptId": rid, "status": "queued"}
        response = execute(db, user["id"], request, body.model_dump(), 202, create)
    request.app.state.training_worker.wake.set()
    return response

@router.get("/trainings/{training_id}/attempts/{attempt_id}", response_model=Envelope[AttemptOut])
def get_attempt(training_id: str, attempt_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        owned(db, "trainings", training_id, user["id"])
        row = owned(db, "attempts", attempt_id, user["id"])
        if row["training_id"] != training_id: fail(404, "作答记录不存在")
        return envelope(attempt_out(row))

@router.post("/trainings/{training_id}/quiz", response_model=Envelope[QuizOut], status_code=201)
def create_quiz(training_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            training = owned(db, "trainings", training_id, user["id"])
            stage = db.execute("SELECT status FROM training_stages WHERE training_id=? AND stage_type='quiz'", (training_id,)).fetchone()
            if stage["status"] != "unlocked": fail(409, "掌握度检测尚未开放")
            rid = new_id()
            question = f"请用自己的话解释「{training['knowledge_point']}」的核心思路，并说明它的适用条件与常见误区。"
            db.execute("INSERT INTO quizzes(id,training_id,question,type,created_at) VALUES (?,?,?,?,?)", (rid, training_id, question, "concept", time.time()))
            return {"quizId": rid, "question": question, "type": "concept"}
        return execute(db, user["id"], request, {}, 201, create)

@router.post("/trainings/{training_id}/quiz/answer", response_model=Envelope[QuizAnswerOut])
def answer_quiz(training_id: str, body: QuizAnswerIn, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            training = owned(db, "trainings", training_id, user["id"])
            quiz = db.execute("SELECT * FROM quizzes WHERE id=? AND training_id=?", (body.quizId, training_id)).fetchone()
            if quiz is None: fail(404, "检测题不存在")
            if quiz["answered_at"] is not None: fail(409, "该检测题已作答")
            exam = db.execute("SELECT course FROM exams WHERE id=?", (training["exam_id"],)).fetchone()
            score = 82.0 if len(body.answer.strip()) >= 10 else 45.0
            concept_correct = score >= 60
            missing = [] if concept_correct else ["回答过于简略，请补充核心思路与适用条件"]
            now = time.time()
            db.execute(
                "UPDATE quizzes SET answer_text=?,score=?,concept_correct=?,missing_points_json=?,answered_at=? WHERE id=?",
                (body.answer, score, 1 if concept_correct else 0, json.dumps(missing, ensure_ascii=False), now, body.quizId),
            )
            db.execute("INSERT OR IGNORE INTO mastery_evidence VALUES (?,?,?,?,?,?,?,?,?)", (new_id(), user["id"], exam["course"], training["knowledge_point_id"], body.quizId, "quiz", score, 100, now))
            mastery_after = compute_mastery(db, user["id"], exam["course"], training["knowledge_point_id"])
            passed = mastery_after is not None and mastery_after >= training["target_mastery"]
            db.execute("UPDATE quizzes SET mastery_after=?,passed=? WHERE id=?", (mastery_after, 1 if passed else 0, body.quizId))
            db.execute("UPDATE training_stages SET status='completed' WHERE training_id=? AND stage_type='quiz'", (training_id,))
            db.execute("UPDATE trainings SET current_mastery=?,status=?,updated_at=? WHERE id=?", (mastery_after, "completed" if passed else training["status"], now, training_id))
            return {"quizId": body.quizId, "score": score, "conceptCorrect": concept_correct, "missingPoints": missing, "masteryAfter": mastery_after, "passed": passed}
        return execute(db, user["id"], request, body.model_dump(), 200, create)

def export_out(db, row):
    result = None
    if row["status"] == "succeeded" and row["file_id"]:
        file = db.execute("SELECT * FROM files WHERE id=?", (row["file_id"],)).fetchone()
        if file: result = {"fileId": file["id"], "fileName": file["original_name"], "downloadUrl": f"/api/v1/files/{file['id']}"}
    return {
        "exportId": row["id"],
        "status": row["status"],
        "result": result,
        "error": json.loads(row["error_json"]) if row["error_json"] else None,
    }

@router.post("/trainings/{training_id}/pdf", response_model=Envelope[ExportAccepted], status_code=202)
def create_export(training_id: str, body: ExportIn, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        def create():
            owned(db, "trainings", training_id, user["id"])
            settings = request.app.state.settings
            rid, now = new_id(), time.time()
            db.execute(
                "INSERT INTO training_exports(id,user_id,training_id,status,include_answers,include_analysis,created_at,ready_at,deadline_at) "
                "VALUES (?,?,?,'queued',?,?,?,?,?)",
                (rid, user["id"], training_id, 1 if body.includeAnswers else 0, 1 if body.includeAnalysis else 0, now, now, now + settings.job_timeout),
            )
            return {"exportId": rid, "status": "queued"}
        response = execute(db, user["id"], request, body.model_dump(), 202, create)
    request.app.state.training_worker.wake.set()
    return response

@router.get("/trainings/{training_id}/pdf/{export_id}", response_model=Envelope[ExportOut])
def get_export(training_id: str, export_id: str, request: Request, user=Depends(current_user)):
    with request.app.state.db.transaction() as db:
        owned(db, "trainings", training_id, user["id"])
        row = owned(db, "training_exports", export_id, user["id"])
        if row["training_id"] != training_id: fail(404, "导出记录不存在")
        return envelope(export_out(db, row))
