"""Conservative quality checks for generated variation questions."""
import re
from difflib import SequenceMatcher

from ..marking.symbolic import check_answer, independent_math_evidence
from ..tool_contracts import VariationQuestion


_FINAL_ANSWER = re.compile(r"(?:最终答案|答案|答)\s*[:：=]\s*([^\n。；;]+)")
_TIER_ORDER = ("consolidation", "reverse", "extension")


def _option_expression(question: VariationQuestion, value: str) -> str:
    label = re.fullmatch(r'(?:选(?:项)?\s*)?([A-Z])[.、]?', value.strip())
    if not label or not question.options:
        return value
    for index, option in enumerate(question.options):
        parsed = re.match(r'^\s*([A-Z])[.、:：)）]\s*(.*)$', option, re.DOTALL)
        key, expression = (parsed.group(1), parsed.group(2)) if parsed else (chr(65 + index), option)
        if key == label.group(1):
            return expression.strip()
    return value


def _answer_verdict(question: VariationQuestion) -> str:
    match = _FINAL_ANSWER.search(question.analysis)
    if not match:
        return "uncertain"
    candidate = match.group(1).strip().strip("$` ")
    return check_answer(question.stem, _option_expression(question, candidate),
                        _option_expression(question, question.answer))["verdict"]


def _knowledge_overlap(source: str, stem: str) -> float:
    source = re.sub(r"\s+", "", source.casefold())
    stem = re.sub(r"\s+", "", stem.casefold())
    if not source or not stem:
        return 0.0
    if source in stem:
        return 1.0
    if len(source) < 3:
        return 1.0 if source in stem else 0.0
    grams = {source[index:index + 2] for index in range(len(source) - 1)}
    return len(grams & {stem[index:index + 2] for index in range(len(stem) - 1)}) / len(grams)


def _duplicate_similarity(left: VariationQuestion, right: VariationQuestion) -> float:
    def normalized(value):
        value = re.sub(r"\d+(?:\.\d+)?", "#", value.casefold())
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)

    first = normalized(left.stem)
    second = normalized(right.stem)
    if not first or not second:
        return 0.0
    return SequenceMatcher(None, first, second).ratio()


def validate_variations(questions: list[VariationQuestion]) -> list[VariationQuestion]:
    """Set contract status from evidence; unsupported math stays pending."""
    checked = []
    for item in questions:
        item = item.model_copy(update={"validation_status": "pending", "reason": None, "warnings": []})
        reason = None
        verdict = _answer_verdict(item)
        evidence = independent_math_evidence(item.stem, item.analysis)
        independent_verdict = "uncertain"
        if evidence["expected"] is not None:
            answer = re.sub(r"^[A-Za-z]\s*=\s*", "", _option_expression(item, item.answer).strip())
            expected = evidence['expected']
            if answer.startswith('{') and not expected.startswith('{'):
                expected = '{' + expected + '}'
            independent_verdict = check_answer(item.stem, answer, expected)["verdict"]
        if not item.stem.strip() or not item.answer.strip() or not item.analysis.strip():
            reason = "题干、答案或解析为空"
        elif independent_verdict == "wrong":
            reason = "题干独立求解结果与提供答案矛盾"
        elif evidence["contradictory_step"]:
            reason = "解析内部计算不等价，存在错误等式"
        elif _knowledge_overlap(item.source_knowledge_point, item.stem) < 0.2:
            reason = "题干与原始考点关键词偏差过大"
        elif verdict == "wrong":
            reason = "解析中的明确最终答案与标准答案矛盾"
        else:
            item = item.model_copy(update={
                "validation_status": "passed" if verdict == "correct" and not evidence.get("uncertain")
                and (evidence["expected"] is None or independent_verdict == "correct") else "pending"
            })
        if reason:
            item = item.model_copy(update={"validation_status": "failed", "reason": reason, "warnings": [reason]})
        checked.append(item)
    # Only compare the requested three-tier group. Similarity after masking
    # numerals catches items that merely replace values while keeping the stem.
    if len(checked) == 3 and {item.tier for item in checked} == set(_TIER_ORDER):
        for left_index, left in enumerate(checked):
            for right_index in range(left_index + 1, len(checked)):
                right = checked[right_index]
                if _duplicate_similarity(left, right) >= 0.82:
                    for index in (left_index, right_index):
                        current = checked[index]
                        reason = current.reason or "同组题目只替换数字或重复题干结构"
                        checked[index] = current.model_copy(update={
                            "validation_status": "failed", "reason": reason,
                            "warnings": current.warnings or [reason]})
    return checked


def validation_reason(question: VariationQuestion) -> str:
    """Return actionable feedback for the next correction round."""
    if question.reason:
        return question.reason + "，请独立核算题干及所有解析步骤后重新设计。"
    if _knowledge_overlap(question.source_knowledge_point, question.stem) < 0.2:
        return "题干偏离原始考点，请围绕该知识点重新设计题干。"
    if _answer_verdict(question) == "wrong":
        return "请重新核算标准答案，并保证解析明确给出相同的最终答案。"
    if _answer_verdict(question) == "uncertain":
        return "请在解析末尾增加可由标准答案直接比较的明确表达式，例如‘最终答案：2’。"
    return "请重新设计题目，避免与同组其他题目只替换数字或重复题干结构。"
