import pytest

from app.services.four_dimension_diagnosis import diagnose_four_dimensions


def test_empty_questions_leave_every_dimension_insufficient():
    result = diagnose_four_dimensions([])

    assert len(result["dimensions"]) == 4
    assert all(item["level"] == "insufficient_evidence" for item in result["dimensions"])
    assert all(item["evidence_count"] == 0 for item in result["dimensions"])
    assert all(item["evidence_question_ids"] == [] for item in result["dimensions"])


def test_wrong_answer_is_mapped_to_one_dimension_with_question_citation():
    result = diagnose_four_dimensions([{
        "questionId": "q7",
        "answers": [{"correct": False, "errorReason": "待定系数负号错误"}],
    }])

    algebra = next(item for item in result["dimensions"]
                   if item["dimension"] == "algebraic_operation")
    assert algebra["level"] == "vulnerable"
    assert algebra["evidence_count"] == 1
    assert algebra["evidence_question_ids"] == ["q7"]
    assert "q7" in algebra["reason"]
    assert "待定系数负号错误" in algebra["reason"]
    assert "q7" in result["markdown"]


@pytest.mark.parametrize("answer", [
    {"correct": None, "errorReason": "符号计算错误"},
    {"correct": True, "errorReason": "符号计算错误"},
    {"correct": False, "errorReason": ""},
])
def test_unjudged_correct_or_unspecified_errors_do_not_create_evidence(answer):
    result = diagnose_four_dimensions([{"questionId": "q1", "answers": [answer]}])

    assert all(item["evidence_count"] == 0 for item in result["dimensions"])


def test_missing_question_id_cannot_be_used_as_evidence():
    result = diagnose_four_dimensions([{
        "answers": [{"correct": False, "errorReason": "待定系数负号错误"}],
    }])

    assert all(item["evidence_count"] == 0 for item in result["dimensions"])


def test_same_question_is_counted_once_per_dimension():
    result = diagnose_four_dimensions([{
        "questionId": "q2",
        "answers": [
            {"correct": False, "errorReason": "移项时符号错误"},
            {"correct": False, "errorReason": "移项符号计算错误"},
        ],
    }])

    algebra = next(item for item in result["dimensions"]
                   if item["dimension"] == "algebraic_operation")
    assert algebra["evidence_count"] == 1
    assert algebra["evidence_question_ids"] == ["q2"]


@pytest.mark.parametrize(("reason", "dimension"), [
    ("定理性质记忆错误", "knowledge_memory"),
    ("移项计算符号错误", "algebraic_operation"),
    ("图像与坐标对应错误", "graphical_combination"),
    ("分类讨论条件遗漏", "logical_reasoning"),
])
def test_each_dimension_uses_explicit_error_signals(reason, dimension):
    result = diagnose_four_dimensions([{
        "questionId": "q3",
        "answers": [{"correct": False, "errorReason": reason}],
    }])

    diagnosis = next(item for item in result["dimensions"] if item["dimension"] == dimension)
    assert diagnosis["evidence_question_ids"] == ["q3"]
    assert diagnosis["evidence_count"] == 1
    assert diagnosis["level"] == "vulnerable"


def test_unmapped_wrong_answer_does_not_get_guessed_into_a_dimension():
    result = diagnose_four_dimensions([{
        "questionId": "q4",
        "answers": [{"correct": False, "errorReason": "题目内容不完整"}],
    }])

    assert all(item["level"] == "insufficient_evidence" for item in result["dimensions"])
    assert "暂无充足证据" in result["markdown"]


def test_repeated_question_evidence_never_implies_proficient():
    questions = [
        {"questionId": f"q{i}", "answers": [{"correct": False, "errorReason": "移项符号错误"}]}
        for i in range(1, 4)
    ]

    result = diagnose_four_dimensions(questions)
    algebra = next(item for item in result["dimensions"]
                   if item["dimension"] == "algebraic_operation")

    assert algebra["level"] == "critical"
    assert algebra["evidence_count"] == 3
    assert algebra["level"] != "proficient"


def test_invalid_input_and_question_limit_are_rejected():
    with pytest.raises(ValueError):
        diagnose_four_dimensions(None)
    with pytest.raises(ValueError):
        diagnose_four_dimensions([{}] * 501)
