"""最终模拟（mock exam）判卷：不同作答必须得到不同评分，并正确推进状态。

这组测试针对集成时的真实风险：最终模拟的判卷逻辑原本写在 grading.py 的旧执行
函数 _execute_grading 里，而当前执行路径已重写为「读 → 判 → 写」三段（判卷与
模型调用在写事务之外）。移植时若漏掉，任务会掉进固定示例分数（MockGrader 的
63/100）。下面用「全对 = 满分、全错 = 0 分」把这种退化解法直接钉死。
"""
import time

from app.mock_bank import _BANK
from test_auth import bearer, client_for, register
from test_business import post, setup_exam

# mock_bank 就是组卷来源，因此这里就是标准答案与分值表。
ANSWER_KEY = {q.questionId: q.correctAnswer for q in _BANK}
MAX_SCORE = {q.questionId: q.maxScore for q in _BANK}
FULL_SCORE = float(sum(MAX_SCORE.values()))
# MockGrader.result() 的固定总分。最终模拟判卷绝不能出现这个值。
FIXED_DEMO_SCORE = 63.0


def grading_client(tmp_path):
    return client_for(tmp_path, job_seconds=.01, marking_mode="disabled")


def wait_terminal(c, auth, grading_id, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = c.get("/api/v1/grading/" + grading_id, headers=auth).json()["data"]
        if data["status"] in ("succeeded", "failed"):
            return data
        time.sleep(.05)
    raise AssertionError(f"grading job {grading_id} never reached a terminal state")


def start_mock(c, auth, exam_id):
    """开一套新的最终模拟卷（force=true 表示「再来一套」）。"""
    created = post(c, f"/exams/{exam_id}/mock?force=true", {}, auth)
    assert created.status_code == 201, created.text
    return created.json()["data"]


def wrong_label(question):
    """挑一个不是正确答案的选项。"""
    correct = ANSWER_KEY[question["questionId"]]
    return next(o["label"] for o in question["options"] if o["label"] != correct)


def submit_and_grade(c, auth, exam_id, mock, answer_for):
    answers = [{"questionId": q["questionId"], "answer": answer_for(q)} for q in mock["questions"]]
    submitted = post(c, f"/exams/{exam_id}/mock/{mock['mockExamId']}/submit", {"answers": answers}, auth)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "submitted"
    accepted = post(c, "/grading", {"examId": exam_id, "mockExamId": mock["mockExamId"]}, auth)
    assert accepted.status_code == 202, accepted.text
    return wait_terminal(c, auth, accepted.json()["data"]["gradingId"])


def test_all_correct_answers_score_full_marks(tmp_path):
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])
        assert mock["status"] == "ready"
        assert all("correctAnswer" not in q for q in mock["questions"]), "标准答案不得下发到前端"

        job = submit_and_grade(c, auth, exam["examId"], mock,
                               lambda q: ANSWER_KEY[q["questionId"]])

        assert job["status"] == "succeeded", job
        result = job["result"]
        assert result["maxScore"] == FULL_SCORE
        assert result["totalScore"] == FULL_SCORE, result
        assert all(q["correct"] is True for q in result["questions"])
        assert job["mockExamId"] == mock["mockExamId"]


def test_all_wrong_answers_score_zero_and_never_the_demo_score(tmp_path):
    """若移植后仍走固定示例分数，这里会拿到 63 分而不是 0 分。"""
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])

        job = submit_and_grade(c, auth, exam["examId"], mock, wrong_label)

        assert job["status"] == "succeeded", job
        result = job["result"]
        assert result["totalScore"] == 0.0, result
        assert result["totalScore"] != FIXED_DEMO_SCORE
        assert all(q["correct"] is False for q in result["questions"])
        assert all(q["errorReason"] for q in result["questions"])
        assert all(q["score"] == 0.0 for q in result["questions"])


def test_different_answers_produce_different_scores(tmp_path):
    """同一场考试连续三套模拟：全对 / 一半对 / 全错，评分必须相应不同。"""
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        scores = {}

        for name, ratio in (("all", 1.0), ("partial", 0.5), ("none", 0.0)):
            mock = start_mock(c, auth, exam["examId"])
            questions = mock["questions"]
            keep = int(len(questions) * ratio)
            correct_ids = {q["questionId"] for q in questions[:keep]}

            def answer_for(q, correct_ids=correct_ids):
                return ANSWER_KEY[q["questionId"]] if q["questionId"] in correct_ids else wrong_label(q)

            job = submit_and_grade(c, auth, exam["examId"], mock, answer_for)
            assert job["status"] == "succeeded", job
            scores[name] = job["result"]["totalScore"]

        assert scores["all"] == FULL_SCORE, scores
        assert scores["none"] == 0.0, scores
        assert 0.0 < scores["partial"] < FULL_SCORE, scores
        assert len(set(scores.values())) == 3, f"三套不同作答得到相同评分：{scores}"
        assert FIXED_DEMO_SCORE not in scores.values()


def test_grading_advances_mock_exam_and_exam_stage(tmp_path):
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])
        assert mock["status"] == "ready"

        job = submit_and_grade(c, auth, exam["examId"], mock,
                               lambda q: ANSWER_KEY[q["questionId"]])

        after = c.get(f'/api/v1/exams/{exam["examId"]}/mock/{mock["mockExamId"]}', headers=auth).json()["data"]
        assert after["status"] == "graded", after
        assert after["gradedAt"] is not None
        assert after["gradingId"] == job["gradingId"]

        refreshed = c.get(f'/api/v1/exams/{exam["examId"]}', headers=auth).json()["data"]
        assert refreshed["stage"] == "completed", refreshed


def test_unsubmitted_mock_exam_is_rejected_and_state_untouched(tmp_path):
    """未提交作答就判卷必须被拒绝，且不能推进状态或产生分数。"""
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])

        rejected = post(c, "/grading", {"examId": exam["examId"], "mockExamId": mock["mockExamId"]}, auth)
        assert rejected.status_code == 409, rejected.text

        after = c.get(f'/api/v1/exams/{exam["examId"]}/mock/{mock["mockExamId"]}', headers=auth).json()["data"]
        assert after["status"] == "ready"
        assert after["gradedAt"] is None
        refreshed = c.get(f'/api/v1/exams/{exam["examId"]}', headers=auth).json()["data"]
        assert refreshed["stage"] != "completed"


def test_mock_exam_job_is_identifiable_in_the_grading_list(tmp_path):
    """判卷记录要带 mockExamId：备考工作台据此把模拟记录留在「最终模拟」板块。"""
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])
        job = submit_and_grade(c, auth, exam["examId"], mock,
                               lambda q: ANSWER_KEY[q["questionId"]])

        listed = c.get(f'/api/v1/exams/{exam["examId"]}/gradings', headers=auth).json()["data"]
        items = listed["items"] if isinstance(listed, dict) else listed
        entry = next(i for i in items if i["gradingId"] == job["gradingId"])
        assert entry["mockExamId"] == mock["mockExamId"]
        assert entry["result"]["totalScore"] == FULL_SCORE


def test_mock_history_and_mistakes_reflect_the_graded_attempt(tmp_path):
    """「最终模拟」板块依赖的两个读取接口：判卷历史与错题集。"""
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])
        job = submit_and_grade(c, auth, exam["examId"], mock, wrong_label)
        assert job["status"] == "succeeded", job

        history = c.get(f'/api/v1/exams/{exam["examId"]}/mock-history', headers=auth).json()["data"]
        entry = next(h for h in history if h["mockExamId"] == mock["mockExamId"])
        assert entry["status"] == "graded"
        assert entry["totalScore"] == 0.0
        assert entry["maxScore"] == FULL_SCORE
        assert entry["gradedAt"] is not None

        mistakes = c.get('/api/v1/mock/mistakes', headers=auth).json()["data"]
        mine = [m for m in mistakes if m["mockExamId"] == mock["mockExamId"]]
        assert len(mine) == len(mock["questions"]), "全错时每道题都应进入错题集"
        for item in mine:
            assert item["userAnswer"] and item["correctAnswer"]
            assert item["userAnswer"] != item["correctAnswer"]
            assert item["score"] == 0.0
            assert item["maxScore"] == MAX_SCORE[item["questionId"]]
            assert item["knowledgePoints"]
            assert item["errorReason"]


def test_another_users_mock_exam_cannot_be_graded(tmp_path):
    with grading_client(tmp_path) as c:
        auth, exam, _ = setup_exam(c)
        mock = start_mock(c, auth, exam["examId"])

        stranger = bearer(register(c, "student_two"))
        refused = post(c, "/grading", {"examId": exam["examId"], "mockExamId": mock["mockExamId"]}, stranger)
        assert refused.status_code == 403, refused.text
