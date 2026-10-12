from app.tool_contracts import VariationQuestion
from app.services.question_validator import validate_variations


def question(tier, stem, answer="x=2", analysis="最终答案：x=2"):
    return VariationQuestion(
        tier=tier,
        source_knowledge_point="一元一次方程",
        difficulty="easy",
        stem=stem,
        answer=answer,
        analysis=analysis,
    )


def test_explicit_conflicting_final_answer_fails_self_consistency():
    item = question("consolidation", "解方程 x+1=3", analysis="最终答案：x=4")

    checked = validate_variations([item])[0]

    assert checked.validation_status == "failed"


def test_unsupported_equation_analysis_stays_pending():
    item = question("consolidation", "解方程 x+1=3", analysis="移项后得到 x=2")

    checked = validate_variations([item])[0]

    assert checked.validation_status == "pending"


def test_knowledge_point_drift_fails():
    item = question("consolidation", "计算三角形面积", analysis="最终答案：x=2")

    checked = validate_variations([item])[0]

    assert checked.validation_status == "failed"


def test_reverse_question_that_only_changes_numbers_fails_as_duplicate():
    items = [
        question("consolidation", "解方程 x+1=3"),
        question("reverse", "已知 x+2=5，求 x"),
        question("extension", "若 x+3=8，求 x"),
    ]

    checked = validate_variations(items)

    assert checked[1].validation_status == "failed"
    assert checked[2].validation_status == "failed"


def test_empty_group_is_safe_and_returns_empty():
    assert validate_variations([]) == []
