"""Three-tier question generation through the configured backend LLM."""
import json
import re

from pydantic import ValidationError

from ..tool_contracts import VariationQuestion
from .question_validator import validate_variations, validation_reason


_TIERS = (
    ("consolidation", "同构巩固", "保持核心方法不变，调整情境或表达以巩固原题考点"),
    ("reverse", "逆向反思", "从答案、条件或结论反推条件，要求反向推理"),
    ("extension", "综合拓展", "组合原考点与相关知识，增加一步推理或应用"),
)


def _parse_question(content: str, expected_tier: str, knowledge_point: str) -> VariationQuestion:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    value = json.loads(content)
    question = VariationQuestion.model_validate(value)
    if question.tier != expected_tier:
        raise ValueError("模型返回的梯次与请求不一致")
    return question.model_copy(update={"source_knowledge_point": knowledge_point})


def _prompt(tier, label, direction, source_question, knowledge_point, feedback=""):
    retry = f"\n针对上次校验问题修正：{feedback}" if feedback else ""
    return f"""为理科练习生成一道变式题。只输出符合给定字段的 JSON 对象，不要 Markdown。
字段：tier, source_knowledge_point, difficulty, stem, options, answer, analysis。
tier 固定为 {tier}，source_knowledge_point 固定为 {json.dumps(knowledge_point, ensure_ascii=False)}。
难度使用 easy、medium、hard。题目方向：{label}。要求：{direction}。
原题：{source_question}
解析末尾使用“最终答案：<表达式>”格式，并确保该表达式与 answer 一致。题干须体现原始考点。{retry}"""


def generate_variation_questions(llm_client, source_question: str,
                                 source_knowledge_point: str) -> dict:
    """Generate one question per tier, validate and retry each failure once."""
    if llm_client is None:
        return {"questions": [], "warnings": ["后端模型未配置，未生成题目"]}
    if not source_question.strip() or not source_knowledge_point.strip():
        return {"questions": [], "warnings": ["原题和原始考点均为必填项"]}

    generated = []
    for tier, label, direction in _TIERS:
        candidate = None
        try:
            response = llm_client.invoke(_prompt(
                tier, label, direction, source_question, source_knowledge_point,
            ))
            candidate = _parse_question(response.content, tier, source_knowledge_point)
        except Exception:
            # Provider and parse failures are retried once through the same
            # correction path and remain failed if no valid question arrives.
            pass
        if candidate is None:
            candidate = VariationQuestion(
                tier=tier,
                source_knowledge_point=source_knowledge_point,
                difficulty="medium",
                stem="",
                answer="",
                analysis="",
                validation_status="failed",
            )
        generated.append(candidate)

    generated = validate_variations(generated)
    for index, item in enumerate(generated):
        if item.validation_status != "failed":
            continue
        tier, label, direction = _TIERS[index]
        try:
            response = llm_client.invoke(_prompt(
                tier, label, direction, source_question, source_knowledge_point,
                validation_reason(item),
            ))
            generated[index] = _parse_question(response.content, tier, source_knowledge_point)
        except Exception:
            # Keep the existing failed item as an auditable warning.
            pass
    generated = validate_variations(generated)
    warnings = []
    for item in generated:
        if item.validation_status == "failed":
            warnings.append(f"{item.tier} 梯次未通过校验，需人工复核")
    return {"questions": generated, "warnings": warnings}
