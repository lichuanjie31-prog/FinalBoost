"""Evidence-linked four-dimension diagnosis from normalized marking results."""
from __future__ import annotations

import re

from ..tool_contracts import DimensionDiagnosis

MAX_QUESTIONS = 500
MAX_ANSWERS = 2000


class DiagnosisResourceLimit(ValueError):
    """Bound the complete marking tree, including child questions and answers."""

DIMENSIONS = (
    ("knowledge_memory", "知识记忆", re.compile(r"概念|定义|定理|公式|记忆|遗忘|性质")),
    ("algebraic_operation", "代数运算", re.compile(r"符号|计算|运算|移项|展开|化简|系数|代入|配方|通分|约分")),
    ("graphical_combination", "图形与几何", re.compile(r"图像|数形|坐标|几何|作图|斜率|面积|位置关系")),
    ("logical_reasoning", "逻辑推理", re.compile(r"推理|逻辑|条件|分类讨论|必要条件|充分条件|漏解|证明|反证|因果")),
)


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _marking_questions(questions):
    pending = [(question, 0) for question in reversed(questions)]
    count = 0
    answer_count = 0
    while pending:
        question, depth = pending.pop()
        if not isinstance(question, dict):
            raise ValueError("题目结构无效")
        if depth > 16:
            raise ValueError("题目嵌套过深")
        count += 1
        answers = question.get("answers")
        children = question.get("children")
        answers = [] if answers is None else answers
        children = [] if children is None else children
        if not isinstance(answers, list) or any(not isinstance(answer, dict) for answer in answers):
            raise ValueError("作答结构无效")
        if not isinstance(children, list):
            raise ValueError("子题结构无效")
        answer_count += len(answers)
        if count + len(pending) + len(children) > MAX_QUESTIONS or answer_count > MAX_ANSWERS:
            raise DiagnosisResourceLimit("批改结果过大")
        yield question
        pending.extend((child, depth + 1) for child in reversed(children))


def _answer_evidence(question: dict) -> tuple[str, str] | None:
    question_id = _text(question.get("questionId"))
    if not question_id:
        return None
    snippets = []
    for answer in question.get("answers") or []:
        if not isinstance(answer, dict) or answer.get("correct") is not False:
            continue
        reason = _text(answer.get("errorReason")) or _text(answer.get("analysis"))
        points = answer.get("knowledgePoints") or []
        if not reason and isinstance(points, list):
            reason = "；".join(_text(point) for point in points if _text(point))
        if reason and reason not in snippets:
            snippets.append(reason)
    if not snippets:
        return None
    return question_id, "；".join(snippets)


def _markdown_card(dimensions: list[dict], citations: dict[str, dict[str, str]]) -> str:
    lines = ["# 四维学情诊断", ""]
    for item in dimensions:
        title = dict((key, label) for key, label, _ in DIMENSIONS)[item["dimension"]]
        lines.extend([f"## {title}", f"判定：{item['level']}（{item['evidence_count']} 条错题证据）"])
        if item["evidence_count"]:
            for question_id in item["evidence_question_ids"]:
                reason = citations[item["dimension"]][question_id]
                lines.append(f"- 证据链：题 `{question_id.replace('`', '')}`：{reason}")
        else:
            lines.append("暂无充足证据，暂不评定能力等级。")
        lines.append("")
    return "\n".join(lines).rstrip()


def diagnose_four_dimensions(questions: list[dict]) -> dict:
    """Classify only explicit wrong-answer evidence with a concrete question ID."""
    if not isinstance(questions, list):
        raise ValueError("questions 必须为数组")
    if len(questions) > MAX_QUESTIONS:
        raise DiagnosisResourceLimit("题目数量异常")

    evidence = {dimension: {} for dimension, _, _ in DIMENSIONS}
    for question in _marking_questions(questions):
        item = _answer_evidence(question)
        if item is None:
            continue
        question_id, reason = item
        for dimension, _, matcher in DIMENSIONS:
            if matcher.search(reason):
                evidence[dimension].setdefault(question_id, reason)

    diagnoses = []
    for dimension, _, _ in DIMENSIONS:
        sources = evidence[dimension]
        count = len(sources)
        level = "insufficient_evidence" if count == 0 else "critical" if count >= 3 else "vulnerable"
        cited_reason = "；".join(f"题 {question_id}：{reason}" for question_id, reason in sources.items())
        diagnosis = DimensionDiagnosis(
            dimension=dimension,
            level=level,
            evidence_count=count,
            evidence_question_ids=list(sources),
            reason=cited_reason or "暂无充足证据，暂不评定。",
        )
        diagnoses.append(diagnosis.model_dump())

    return {
        "dimensions": diagnoses,
        "markdown": _markdown_card(diagnoses, evidence),
    }
