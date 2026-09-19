"""The chat must be able to read the cloud marking results.

A marking batch is passed as its own field (``markingJobIds``) rather than being
smuggled into the legacy ``gradingId``, so the old grading flow keeps working
while a marking batch reaches the model as real question content.
"""
import json
import time

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, SystemMessage
from app.agent.tools import _query_marking_questions_impl, _query_wrong_questions_impl
from app.main import create_app
from test_auth import HEADERS, bearer, register
from test_business import setup_exam
from test_agent_graph import StrictModel

TERMINAL = {"succeeded", "failed", "submission_unknown"}

# The fixture provider's own dataset — the assertions below read it back out of
# the model prompt, so they must match app/marking/fixture.py.
FIXTURE_STEM = "第 2 题 判断级数敛散性"
FIXTURE_STUDENT = "收敛"
FIXTURE_RIGHT = "发散"
FIXTURE_ANALYSIS = "调和级数发散，通项趋于零不能推出级数收敛。"
FIXTURE_POINT = "调和级数"
FIXTURE_ERROR = "误判调和级数敛散性"


def marking_client(tmp_path, **kwargs):
    return TestClient(create_app(data_dir=tmp_path, grading_mode="mock", llm_api_key="",
                                 job_seconds=.01, rag_enabled=False, marking_mode="fixture", **kwargs))


def create_marking_job(c, auth, exam, file, request_key="page-1"):
    """Submit one page to the fixture provider and wait for it to finish."""
    accepted = c.post("/api/v1/marking/jobs",
                      json={"examId": exam["examId"], "fileId": file["fileId"], "requestKey": request_key},
                      headers=auth)
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["data"]["jobId"]
    for _ in range(60):
        job = c.get("/api/v1/marking/jobs/" + job_id, headers=auth).json()["data"]
        if job["status"] in TERMINAL:
            return job
        time.sleep(.02)
    raise AssertionError(f"marking job {job_id} never reached a terminal state")


def system_prompt_of(model, call=0):
    return "\n".join(m.content for m in model.seen[call] if isinstance(m, SystemMessage))


def test_chat_sends_the_marked_question_content_to_the_model(tmp_path, monkeypatch):
    """A finished fixture batch must reach the model as题目、作答、判定、解析、知识点."""
    from app.agent import router

    model = StrictModel([AIMessage(content="第 2 题你把调和级数判成了收敛。")])
    monkeypatch.setattr(router, "_get_llm", lambda request: model)

    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        job = create_marking_job(c, auth, exam, file)
        assert job["status"] == "succeeded"
        assert job["result"]["totalScore"] is None

        response = c.post("/api/v1/agent/chat", json={
            "message": "我这次错在哪", "examId": exam["examId"],
            "markingJobIds": [job["jobId"]],
        }, headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["message"] == "第 2 题你把调和级数判成了收敛。"

    prompt = system_prompt_of(model)
    assert FIXTURE_STEM in prompt, "the question stem never reached the model"
    assert FIXTURE_STUDENT in prompt and FIXTURE_RIGHT in prompt
    assert FIXTURE_ANALYSIS in prompt and FIXTURE_POINT in prompt and FIXTURE_ERROR in prompt
    assert "未判定" not in prompt, "the fixture batch decides every answer"
    # No score basis exists, so none may be stated.
    assert "未计算分数" in prompt and "不要推测或编造分数" in prompt


def test_marking_ids_are_passed_separately_from_the_legacy_grading_id(tmp_path, monkeypatch):
    """The marking batch travels in its own field; grading_id stays untouched."""
    from app.agent import graph, router

    seen = {}
    monkeypatch.setattr(router, "_get_llm", lambda request: object())

    def fake_run_agent(**kwargs):
        seen.update(kwargs)
        return {"content": "已读取批改结果。", "tool_calls": [], "tool_calls_json": None}

    monkeypatch.setattr(graph, "run_agent", fake_run_agent)

    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        job = create_marking_job(c, auth, exam, file)

        response = c.post("/api/v1/agent/chat", json={
            "message": "分析一下", "examId": exam["examId"], "markingJobIds": [job["jobId"]],
        }, headers=auth)
        assert response.status_code == 200, response.text
        assert seen["marking_job_ids"] == [job["jobId"]]
        assert seen["grading_id"] is None, "a marking id must never be smuggled into grading_id"
        assert seen["exam_id"] == exam["examId"]

        # ...and the legacy id space is still enforced: a marking id is not a grading id.
        smuggled = c.post("/api/v1/agent/chat",
                          json={"message": "分析一下", "gradingId": job["jobId"]}, headers=auth)
        assert smuggled.status_code == 404, smuggled.text


def test_other_users_marking_job_is_rejected(tmp_path, monkeypatch):
    from app.agent import router

    monkeypatch.setattr(router, "_get_llm", lambda request: object())
    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        job = create_marking_job(c, auth, exam, file)

        body = {"message": "分析一下", "examId": exam["examId"], "markingJobIds": [job["jobId"]]}
        assert c.post("/api/v1/agent/chat", json=body).status_code == 401
        stranger = {**HEADERS, **bearer(register(c, "student_two"))}
        assert c.post("/api/v1/agent/chat", json=body, headers=stranger).status_code == 403


def test_marking_job_from_another_exam_is_rejected(tmp_path, monkeypatch):
    from app.agent import router
    from test_business import exam_body, post

    monkeypatch.setattr(router, "_get_llm", lambda request: object())
    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        job = create_marking_job(c, auth, exam, file)
        other = post(c, "/exams", exam_body(course="英语"), auth).json()["data"]

        response = c.post("/api/v1/agent/chat", json={
            "message": "分析一下", "examId": other["examId"], "markingJobIds": [job["jobId"]],
        }, headers=auth)
        assert response.status_code == 400, response.text


def test_unfinished_marking_job_is_rejected(tmp_path, monkeypatch):
    """A batch that did not succeed is refused instead of analysed as if it had."""
    from app.agent import router
    from test_business import exam_body, post

    monkeypatch.setattr(router, "_get_llm", lambda request: object())
    monkeypatch.setenv("MARKING_FIXTURE_SCENARIO", "provider_error")
    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        job = create_marking_job(c, auth, exam, file)
        assert job["status"] == "failed", job

        response = c.post("/api/v1/agent/chat", json={
            "message": "分析一下", "examId": exam["examId"], "markingJobIds": [job["jobId"]],
        }, headers=auth)
        assert response.status_code == 409, response.text


def craft_job(c, exam, file, result, status="succeeded", page_index=0):
    """Store a marking job whose stored result is shaped exactly as given."""
    job_id = "crafted-" + str(page_index)
    with c.app.state.db.transaction() as conn:
        user_id = conn.execute("SELECT user_id FROM exams WHERE id=?", (exam["examId"],)).fetchone()["user_id"]
        conn.execute(
            "INSERT INTO marking_jobs(id,user_id,exam_id,file_id,request_key,fingerprint,status,"
            "image_json,result_json,page_index,provider,created_at,last_poll) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, user_id, exam["examId"], file["fileId"], job_id, "fp", status,
             "{}", json.dumps(result, ensure_ascii=False), page_index, "fixture", time.time(), 0),
        )
    return job_id


def undetermined_result():
    """One answer the provider never judged, and one it did."""
    return {
        "questions": [
            {"questionId": "1", "text": "题干：未判定题", "rightAnswer": "", "children": [],
             "answers": [{"answerId": "1.a1", "handwriting": "学生写的A", "correct": None,
                          "analysis": "解析A", "rightAnswer": "标准答案B",
                          "knowledgePoints": ["知识点A"], "errorReason": ""}]},
            {"questionId": "2", "text": "题干：错题", "rightAnswer": "", "children": [],
             "answers": [{"answerId": "2.a1", "handwriting": "学生写的C", "correct": False,
                          "analysis": "解析C", "rightAnswer": "标准答案D",
                          "knowledgePoints": ["知识点C"], "errorReason": "算错了"}]},
        ],
        "totalScore": None, "maxScore": None, "scoreStatus": "unavailable",
    }


def test_undetermined_judgement_stays_unknown(tmp_path, monkeypatch):
    """A verdict the provider never gave must not be reported as a wrong answer."""
    from app.agent import router

    model = StrictModel([AIMessage(content="我看了你的批改结果。")])
    monkeypatch.setattr(router, "_get_llm", lambda request: model)

    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        job_id = craft_job(c, exam, file, undetermined_result())
        db = c.app.state.db

        with db.transaction() as conn:
            user_id = conn.execute("SELECT user_id FROM exams WHERE id=?", (exam["examId"],)).fetchone()["user_id"]

        detail = json.loads(_query_marking_questions_impl(db, user_id, exam["examId"], [job_id]))
        assert detail["total"] == 2 and detail["undetermined"] == 1
        assert detail["scoreAvailable"] is False
        verdicts = {q["questionText"]: q["verdict"] for q in detail["questions"]}
        assert verdicts["题干：未判定题"] == "未判定"
        assert verdicts["题干：错题"] == "错误"

        # The wrong-question tool reports only the answer that was actually wrong.
        wrong = json.loads(_query_wrong_questions_impl(db, user_id, exam["examId"]))
        assert wrong["total"] == 1
        assert wrong["wrongQuestions"][0]["questionText"] == "题干：错题"
        assert wrong["wrongQuestions"][0]["source"] == "marking"
        assert wrong["wrongQuestions"][0]["score"] is None

        response = c.post("/api/v1/agent/chat", json={
            "message": "我错在哪", "examId": exam["examId"], "markingJobIds": [job_id],
        }, headers=auth)
        assert response.status_code == 200, response.text

    prompt = system_prompt_of(model)
    assert "判定：未判定" in prompt
    assert "1 题未能判定正误" in prompt
    assert "题干：未判定题" in prompt and "题干：错题" in prompt


def test_marking_batch_must_belong_to_one_exam(tmp_path, monkeypatch):
    """Two pages of one paper are fine; two papers in one batch are not."""
    from app.agent import router
    from test_business import exam_body, post

    monkeypatch.setattr(router, "_get_llm", lambda request: StrictModel([AIMessage(content="收到。")]))
    with marking_client(tmp_path) as c:
        user_auth, exam, file = setup_exam(c)
        auth = {**HEADERS, **user_auth}
        first = create_marking_job(c, auth, exam, file, request_key="page-1")

        # Repeating the same page id inside one batch is de-duplicated, not an error.
        same_paper = c.post("/api/v1/agent/chat", json={
            "message": "分析一下", "examId": exam["examId"],
            "markingJobIds": [first["jobId"], first["jobId"]],
        }, headers=auth)
        assert same_paper.status_code == 200, same_paper.text

        # A batch spanning two exams is refused.
        second_exam = post(c, "/exams", exam_body(course="英语"), auth).json()["data"]
        foreign = craft_job(c, second_exam, file, undetermined_result(), page_index=7)
        mixed = c.post("/api/v1/agent/chat", json={
            "message": "分析一下", "examId": exam["examId"],
            "markingJobIds": [first["jobId"], foreign],
        }, headers=auth)
        assert mixed.status_code == 400, mixed.text
