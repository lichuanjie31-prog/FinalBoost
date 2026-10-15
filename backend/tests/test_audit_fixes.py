"""Regression probes for the submission audit, using real MCP and PDF output."""
import base64
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.mcp_bridge import create_mcp_server
from app.materials import MaterialPdfIn, material_pdf
from app.services.question_validator import validate_variations
from app.tool_contracts import VariationQuestion


def variation(**values):
    return VariationQuestion(tier="consolidation", source_knowledge_point="一元一次方程",
                             difficulty="easy", stem="一元一次方程：解 x+1=3",
                             **values)


def tool(name):
    return create_mcp_server()._tool_manager.get_tool(name).fn


def test_probe_1_self_consistent_wrong_answer_is_failed():
    result = validate_variations([variation(answer="999", analysis="最终答案：999")])[0]
    assert result.validation_status == "failed"
    assert "题干独立求解结果与提供答案矛盾" in result.reason


@pytest.mark.parametrize("status", ["failed", "pending"])
@pytest.mark.parametrize("field", ["validation_status", "validationStatus"])
def test_probe_2_rejected_candidates_never_produce_pdf(status, field):
    result = tool("generate_practice_pdf")(
        sections=[{"questions": [{"stem": "x+1=3", field: status}]}])
    assert result.get("error_code") == "PARSE_FAILED"
    assert "base64" not in result
    assert result.get("fallback_payload") is None


def test_http_pdf_rejects_all_failed_with_422():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        material_pdf(MaterialPdfIn(sections=[{"questions": [{
            "stem": "x+1=3", "validation_status": "failed"}]}]))
    assert error.value.status_code == 422


@pytest.mark.parametrize("alias", [False, True])
def test_probe_3_variation_options_and_dumate_pdf_have_separate_answers(alias):
    question = variation(answer="2", analysis="移项求解。最终答案：2",
                         options=["A. 2", "B. 3"], validation_status="passed")
    if alias:
        section = {"sectionTitle": "一元一次方程", "problems": [{
            "content": question.stem, "options": question.options,
            "answer": "2", "analysis": question.analysis, "validationStatus": "passed"}]}
    else:
        section = {"knowledgePoint": "一元一次方程", "questions": [question.model_dump()]}
    result = tool("generate_practice_pdf")(sections=[section], includeAnswers=True, includeAnalysis=True)
    assert result.get("mimeType") == "application/pdf", result
    reader = PdfReader(BytesIO(base64.b64decode(result["base64"])))
    assert len(reader.pages) >= 2
    front = reader.pages[0].extract_text()
    back = "\n".join(page.extract_text() for page in reader.pages[1:])
    assert "参考答案" not in front and "最终答案" not in front
    assert "A. 2" in front and "B. 3" in front
    assert "参考答案与名师解析" in back
    assert "最终答案：2" in back


def test_probe_4_flat_wrong_answers_cluster_by_standard_code():
    result = tool("analyze_weak_points")(questions=[
        {"questionId": "p1", "correct": False, "knowledgePoints": ["动量结合"]},
        {"questionId": "p2", "correct": False,
         "knowledgePoints": ["电磁感应·导体棒模型·动量结合"]},
    ])
    assert len(result["weakPoints"]) == 1
    point = result["weakPoints"][0]
    assert point["code"] == "PHYS-MOM-01"
    assert point["standardName"] == "动量守恒"
    assert point["wrongCount"] == 2
    assert point["questionIds"] == ["p1", "p2"]
    assert point["errorRate"] == 1 and point["accuracyRate"] == 0
    assert point["totalScore"] is None and point["scoreLossRate"] is None


@pytest.mark.parametrize("stem,answer", [
    ("解方程 x^2-4=0", "{2}"), ("解方程 1/(x-1)=2", "2"),
    ("解方程 sqrt(x+1)=3", "3"), ("计算 1+1", "3"),
])
def test_independent_equations_and_evaluation_reject_wrong_answers(stem, answer):
    question = variation(answer=answer, analysis=f"最终答案：{answer}").model_copy(
        update={"stem": "一元一次方程：" + stem})
    assert validate_variations([question])[0].validation_status == "failed"


def test_false_arithmetic_in_word_problem_analysis_is_failed():
    question = variation(answer="2", analysis="先计算 1+1=3。最终答案：2").model_copy(
        update={"stem": "一元一次方程应用，小明买苹果，求数量"})
    assert validate_variations([question])[0].validation_status == "failed"


@pytest.mark.parametrize("top", ["groups", "problems", "questions"])
def test_top_level_pdf_aliases(top):
    result = tool("generate_practice_pdf")(**{top: [{"text": "1+1=?"}]})
    assert result.get("mimeType") == "application/pdf", result


def test_marking_aliases_preserve_id_stem_and_false_judgement():
    result = tool("normalize_marking_result")(questions=[{
        "questionNumber": "q9", "content": "1+1=?", "student_answer": "3",
        "correct_answer": "2", "is_correct": False, "knowledgePoints": ["整式运算"]}])
    question = result["questions"][0]
    assert question["questionId"] == "q9"
    assert question["text"] == "1+1=?"
    assert question["answers"][0]["correct"] is False


def test_option_dict_aliases_and_unlabelled_strings():
    body = MaterialPdfIn(sections=[{"questions": [{"stem": "选择正确结果", "options": [
        "2", "B. 3", {"label": "C", "content": "4"}, {"key": "D", "value": "5"}]}]}])
    assert body.sections[0].questions[0].options == [
        {"key": "A", "text": "2"}, {"key": "B", "text": "3"},
        {"key": "C", "text": "4"}, {"key": "D", "text": "5"}]


def test_three_generation_rounds_can_repair_second_retry():
    import json
    from app.services.variation_questions import generate_variation_questions
    class Model:
        def __init__(self):
            self.rounds = {}
        def invoke(self, prompt):
            tier = next(t for t in ("consolidation", "reverse", "extension") if f"tier 固定为 {t}" in prompt)
            self.rounds[tier] = self.rounds.get(tier, 0) + 1
            stems = {"consolidation": "解一元一次方程 x+1=3",
                     "reverse": "一元一次方程已知解为 2，求常数",
                     "extension": "一元一次方程应用，求苹果数量"}
            answer = "999" if tier == "consolidation" and self.rounds[tier] < 3 else "2"
            data = {"tier": tier, "source_knowledge_point": "一元一次方程", "difficulty": "easy",
                    "stem": stems[tier], "answer": answer, "analysis": f"最终答案：{answer}"}
            return type("Response", (), {"content": json.dumps(data, ensure_ascii=False)})()
    model = Model()
    result = generate_variation_questions(model, "解 x+1=3", "一元一次方程")
    assert result["questions"][0].validation_status == "passed"
    assert model.rounds["consolidation"] == 3
    assert result["warnings"] == []


def test_math_sanitizer_handles_nested_fraction_and_commands():
    from app.pdf import sanitize_math_text
    assert sanitize_math_text(r"bb(R) \mathbb{R} infinity \infty") == "R（实数集） R（实数集） ∞ ∞"
    assert sanitize_math_text(r"\frac{1+\sqrt{x}}{2} <= \pi") == "(1+√(x))/(2) ≤ π"
    assert sanitize_math_text(r"\alpha \beta \gamma \theta \lambda \Delta \in \cup \cap \subset \neq \ge") == "α β γ θ λ Δ ∈ ∪ ∩ ⊂ ≠ ≥"


def test_mixed_quality_paper_filters_rejected_questions_and_number_labels():
    result = tool('generate_practice_pdf')(sections=[{'questions': [
        {'stem': 'REJECTED_STEM', 'validation_status': 'failed', 'answer': 'REJECTED_ANSWER'},
        {'stem': 'GOOD_STEM', 'options': [{'key': '1', 'text': 'yes'}, {'key': '2', 'text': 'no'}],
         'answer': 'yes', 'validation_status': 'passed'}]}], includeAnswers=True)
    reader = PdfReader(BytesIO(base64.b64decode(result['base64'])))
    texts = [page.extract_text() for page in reader.pages]
    assert 'REJECTED' not in '\n'.join(texts)
    assert 'A. yes' in texts[0] and 'B. no' in texts[0]
    assert '1. yes' not in texts[0]


def test_conflicting_quality_aliases_cannot_reopen_pdf_gate():
    result = tool('generate_practice_pdf')(sections=[{'questions': [{
        'stem': 'x=2', 'validation_status': 'passed', 'validationStatus': 'failed'}]}])
    assert result['error_code'] == 'PARSE_FAILED'


def test_scored_and_unscored_statistics_use_distinct_rates():
    questions = [{'questionId': '1', 'answers': [{'correct': False,
        'knowledgePoints': ['动量结合', '动量守恒'], 'score': 2, 'maxScore': 10}]},
        {'questionId': '2', 'answers': [{'correct': True, 'knowledgePoints': ['动量守恒'],
                                      'score': 10, 'maxScore': 10}]}]
    result = tool('analyze_weak_points')(questions=questions)['weakPoints'][0]
    assert result['wrongCount'] == 1 and result['correctCount'] == 1
    assert result['totalScore'] == 12 and result['maxScore'] == 20
    assert result['scoreLossRate'] == .4
    assert result['errorRate'] == .5 and result['accuracyRate'] == .5
    questions[1]['answers'][0]['score'] = None
    result = tool('analyze_weak_points')(questions=questions)['weakPoints'][0]
    assert result['totalScore'] is None and result['scoreLossRate'] is None


def test_four_dimension_flat_evidence_exposes_standard_topic():
    result = tool('analyze_four_dimension_diagnosis')(questions=[{
        'questionId': 'p1', 'correct': False, 'knowledgePoints': ['电磁感应·导体棒模型·动量结合'],
        'errorReason': '动量守恒公式记忆错误'}])
    assert result['knowledgePoints'] == [{'code': 'PHYS-MOM-01', 'standardName': '动量守恒'}]
    assert result['dimensions'][0]['evidence_question_ids'] == ['p1']


@pytest.mark.parametrize('stem,answer', [
    ('解方程 x^2-4=0', '{-2,2}'), ('解方程 1/(x-1)=2', '3/2'),
    ('解方程 sqrt(x+1)=3', '8'), ('解方程 x+1=3', '{2}')])
def test_independent_solver_accepts_full_real_solution_set(stem, answer):
    item = variation(answer=answer, analysis=f'最终答案：{answer}').model_copy(
        update={'stem': '一元一次方程：' + stem})
    assert validate_variations([item])[0].validation_status == 'passed'


def test_no_solution_equation_cannot_pass_with_numeric_answer():
    item = variation(answer='2', analysis='最终答案：2').model_copy(
        update={'stem': '一元一次方程：解方程 x+1=x+2'})
    assert validate_variations([item])[0].validation_status == 'failed'


@pytest.mark.parametrize('stem', [
    '一元一次方程 x+1=3', r'一元一次方程：解 \(x+1=3\)',
    '一元一次方程：解 x−1=3'])
def test_equation_without_solve_prefix_and_math_delimiters_are_checked(stem):
    item = variation(answer='999', analysis='最终答案：999').model_copy(update={'stem': stem})
    assert validate_variations([item])[0].validation_status == 'failed'


@pytest.mark.parametrize('answer,status', [('2', 'failed'), ('8', 'passed')])
def test_unicode_radical_is_solved_without_losing_root_operator(answer, status):
    item = variation(answer=answer, analysis=f'最终答案：{answer}').model_copy(
        update={'stem': '解一元一次方程 √(x+1)=3'})
    assert validate_variations([item])[0].validation_status == status


@pytest.mark.parametrize('answer,status', [('A', 'passed'), ('B', 'failed')])
def test_choice_label_is_resolved_before_independent_comparison(answer, status):
    item = variation(answer=answer, analysis=f'最终答案：{answer}', options=['A. 2', 'B. 3'])
    assert validate_variations([item])[0].validation_status == status


@pytest.mark.parametrize('stem,answer,status', [
    ('一元一次方程：解 x+1=3，其中 y=5', '999', 'failed'),
    ('一元一次方程：解 x+1=3，其中 y=5', '2', 'passed'),
    ('一元一次方程：解 x+1=3，且 x=4', '2', 'failed'),
    ('一元一次方程：解 x+y=3', '2', 'pending'),
])
def test_additional_equations_do_not_bypass_independent_validation(stem, answer, status):
    item = variation(answer=answer, analysis=f'最终答案：{answer}').model_copy(update={'stem': stem})
    assert validate_variations([item])[0].validation_status == status
