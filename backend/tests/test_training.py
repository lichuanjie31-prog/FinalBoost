import uuid
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from test_auth import client_for, register, bearer

def exam_body():
    return {"course": "数据结构", "examDate": (datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=7)).isoformat(), "targetScore": 85}

def post(c, path, data, auth, key=None):
    return c.post("/api/v1" + path, json=data, headers={**auth, "Idempotency-Key": key or str(uuid.uuid4())})

def setup_training(c, **overrides):
    auth = bearer(register(c))
    exam = post(c, "/exams", exam_body(), auth).json()["data"]
    body = {"examId": exam["examId"], "knowledgePointId": "kp001", "targetMastery": 80, **overrides}
    return auth, exam, body

def test_create_training_initializes_stages_and_idempotency(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        key = str(uuid.uuid4())
        first = post(c, "/trainings", body, auth, key)
        assert first.status_code == 201, first.text
        data = first.json()["data"]
        assert [s["type"] for s in data["stages"]] == ["method", "guided", "easy", "medium", "quiz"]
        assert data["stages"][0]["status"] == "unlocked"
        assert all(s["status"] == "locked" for s in data["stages"][1:])
        assert data["targetMastery"] == 80 and data["currentMastery"] is None
        assert data["title"] == "kp001 专项突破"
        assert post(c, "/trainings", body, auth, key).json()["data"]["trainingId"] == data["trainingId"]
        assert post(c, "/trainings", {**body, "targetMastery": 90}, auth, key).status_code == 409

def test_stage_unlock_order_locked_access_and_completion_rules(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        tid = post(c, "/trainings", body, auth).json()["data"]["trainingId"]
        method = c.get(f"/api/v1/trainings/{tid}/stages/method", headers=auth)
        assert method.status_code == 200 and method.json()["data"]["status"] == "unlocked"
        assert method.json()["data"]["content"]
        assert c.get(f"/api/v1/trainings/{tid}/stages/guided", headers=auth).status_code == 409
        assert post(c, f"/trainings/{tid}/stages/quiz/complete", {}, auth).status_code == 409
        done = post(c, f"/trainings/{tid}/stages/method/complete", {}, auth)
        assert done.status_code == 200 and done.json()["data"]["nextStageType"] == "guided"
        assert post(c, f"/trainings/{tid}/stages/method/complete", {}, auth).status_code == 409
        guided = c.get(f"/api/v1/trainings/{tid}/stages/guided", headers=auth).json()["data"]
        assert guided["status"] == "unlocked" and len(guided["questions"]) == 2
        assert post(c, f"/trainings/{tid}/stages/guided/complete", {}, auth).status_code == 409
        assert c.get(f"/api/v1/trainings/{tid}/stages/easy", headers=auth).status_code == 409

def test_list_trainings_by_user(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        assert c.get("/api/v1/trainings", headers=auth).json()["data"]["items"] == []
        tid = post(c, "/trainings", body, auth).json()["data"]["trainingId"]
        items = c.get("/api/v1/trainings", headers=auth).json()["data"]["items"]
        assert len(items) == 1 and items[0]["trainingId"] == tid

def test_pdf_export_generates_downloadable_file(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        tid = post(c, "/trainings", body, auth).json()["data"]["trainingId"]
        assert post(c, f"/trainings/{tid}/pdf", {"includeAnalysis": True}, auth).status_code == 400
        accepted = post(c, f"/trainings/{tid}/pdf", {"includeAnswers": True, "includeAnalysis": True}, auth)
        assert accepted.status_code == 202, accepted.text
        eid = accepted.json()["data"]["exportId"]
        deadline = time.monotonic() + 10
        data = None
        while time.monotonic() < deadline:
            data = c.get(f"/api/v1/trainings/{tid}/pdf/{eid}", headers=auth).json()["data"]
            if data["status"] in ("succeeded", "failed"): break
            time.sleep(0.05)
        assert data["status"] == "succeeded", data
        assert data["result"]["fileName"].endswith(".pdf")
        download = c.get(data["result"]["downloadUrl"], headers=auth)
        assert download.status_code == 200 and download.headers["content-type"] == "application/pdf"
        assert download.content[:5] == b"%PDF-"
        other = bearer(register(c, "student_two"))
        assert c.get(f"/api/v1/trainings/{tid}/pdf/{eid}", headers=other).status_code == 403

def test_training_isolation_and_unknown_stage(tmp_path):
    with client_for(tmp_path) as c:
        owner, exam, body = setup_training(c)
        tid = post(c, "/trainings", body, owner).json()["data"]["trainingId"]
        other = bearer(register(c, "student_two"))
        assert c.get(f"/api/v1/trainings/{tid}", headers=other).status_code == 403
        assert c.get(f"/api/v1/trainings/{tid}").status_code == 401
        assert c.get(f"/api/v1/trainings/{tid}/stages/nope", headers=owner).status_code == 404

def answer(c, auth, tid, question_id, value="A"):
    r = post(c, f"/trainings/{tid}/attempts", {"questionId": question_id, "answer": value, "durationSeconds": 60}, auth)
    assert r.status_code == 202, r.text
    return r.json()["data"]["attemptId"]

def wait_attempt(c, auth, tid, aid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        data = c.get(f"/api/v1/trainings/{tid}/attempts/{aid}", headers=auth).json()["data"]
        if data["status"] in ("succeeded", "failed"): return data
        time.sleep(0.05)
    raise AssertionError("attempt did not reach terminal status")

def complete(c, auth, tid, stage, expected_next):
    r = post(c, f"/trainings/{tid}/stages/{stage}/complete", {}, auth)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["nextStageType"] == expected_next
    return r

def test_attempt_grades_and_updates_mastery(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        tid = post(c, "/trainings", body, auth).json()["data"]["trainingId"]
        complete(c, auth, tid, "method", "guided")
        assert post(c, f"/trainings/{tid}/attempts", {"questionId": "easy_1", "answer": "A", "durationSeconds": 10}, auth).status_code == 409
        assert post(c, f"/trainings/{tid}/attempts", {"questionId": "nope", "answer": "A", "durationSeconds": 10}, auth).status_code == 404
        result = wait_attempt(c, auth, tid, answer(c, auth, tid, "guided_1", "a"))
        assert result["result"]["correct"] is True and result["result"]["score"] == 8
        assert result["result"]["masteryBefore"] is None and result["result"]["masteryAfter"] == 100.0
        wrong = wait_attempt(c, auth, tid, answer(c, auth, tid, "guided_2", "B"))
        assert wrong["result"]["correct"] is False and wrong["result"]["score"] == 0
        assert c.get(f"/api/v1/trainings/{tid}", headers=auth).json()["data"]["currentMastery"] is not None

def test_photo_attempt_and_full_stage_progression(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        tid = post(c, "/trainings", body, auth).json()["data"]["trainingId"]
        complete(c, auth, tid, "method", "guided")
        for i in (1, 2):
            wait_attempt(c, auth, tid, answer(c, auth, tid, f"guided_{i}"))
        complete(c, auth, tid, "guided", "easy")
        for i in (1, 2, 3):
            wait_attempt(c, auth, tid, answer(c, auth, tid, f"easy_{i}"))
        complete(c, auth, tid, "easy", "medium")
        for i in (1, 2):
            wait_attempt(c, auth, tid, answer(c, auth, tid, f"medium_{i}"))
        complete(c, auth, tid, "medium", "quiz")
        assert post(c, f"/trainings/{tid}/quiz", {}, auth).status_code == 201

def test_quiz_requires_unlock_and_answers_once(tmp_path):
    with client_for(tmp_path) as c:
        auth, exam, body = setup_training(c)
        tid = post(c, "/trainings", body, auth).json()["data"]["trainingId"]
        assert post(c, f"/trainings/{tid}/quiz", {}, auth).status_code == 409
        complete(c, auth, tid, "method", "guided")
        for i in (1, 2):
            wait_attempt(c, auth, tid, answer(c, auth, tid, f"guided_{i}"))
        complete(c, auth, tid, "guided", "easy")
        for i in (1, 2, 3):
            wait_attempt(c, auth, tid, answer(c, auth, tid, f"easy_{i}"))
        complete(c, auth, tid, "easy", "medium")
        for i in (1, 2):
            wait_attempt(c, auth, tid, answer(c, auth, tid, f"medium_{i}"))
        complete(c, auth, tid, "medium", "quiz")
        quiz = post(c, f"/trainings/{tid}/quiz", {}, auth).json()["data"]
        answer_body = {"quizId": quiz["quizId"], "answer": "核心思路是先确定最短距离再松弛相邻边，适用于非负权图。"}
        first = post(c, f"/trainings/{tid}/quiz/answer", answer_body, auth)
        assert first.status_code == 200, first.text
        data = first.json()["data"]
        assert data["score"] == 82 and data["passed"] is True and data["masteryAfter"] is not None
        assert post(c, f"/trainings/{tid}/quiz/answer", answer_body, auth).status_code == 409
        detail = c.get(f"/api/v1/trainings/{tid}", headers=auth).json()["data"]
        assert detail["stages"][-1]["status"] == "completed"
