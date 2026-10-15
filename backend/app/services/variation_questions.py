"""Three-tier question generation through the configured backend LLM."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait

from pydantic import ValidationError
from openai import APITimeoutError

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
                                 source_knowledge_point: str, *, parallel=False,
                                 budget_seconds=105) -> dict:
    """Generate each tier in at most three rounds, retaining rejected evidence."""
    if llm_client is None:
        return {"questions": [], "warnings": ["后端模型未配置，未生成题目"]}
    if not source_question.strip() or not source_knowledge_point.strip():
        return {"questions": [], "warnings": ["原题和原始考点均为必填项"]}

    generated = []
    provider_errors = {}
    deadline = time.monotonic() + budget_seconds

    def request_round(requests):
        if not parallel:
            return [(index, fetch(index, feedback)) for index, feedback in requests]
        executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='practice')
        try:
            futures = {executor.submit(fetch, index, feedback): index for index, feedback in requests}
            done, pending = wait(futures, timeout=max(0, deadline - time.monotonic()))
            result = [(futures[future], future.result()) for future in done]
            for future in pending:
                future.cancel()
                provider_errors[_TIERS[futures[future]][0]] = 'TIMEOUT'
                result.append((futures[future], None))
            return result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def fetch(index, feedback):
        if time.monotonic() >= deadline:
            provider_errors[_TIERS[index][0]] = 'TIMEOUT'
            return None
        tier, label, direction = _TIERS[index]
        try:
            response = invoke(_prompt(tier, label, direction, source_question,
                                      source_knowledge_point, feedback), tier)
            return _parse_question(response.content, tier, source_knowledge_point)
        except Exception:
            return None

    def invoke(prompt, tier):
        try:
            response = llm_client.invoke(prompt)
        except (TimeoutError, APITimeoutError):
            provider_errors[tier] = "TIMEOUT"
            raise
        except Exception:
            provider_errors[tier] = "SERVICE_DEGRADED"
            raise
        provider_errors.pop(tier, None)
        return response

    candidates = dict(request_round([(index, '') for index in range(3)]))
    for index, (tier, label, direction) in enumerate(_TIERS):
        candidate = candidates.get(index)
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
    for _ in range(2):
        failed = [(index, item) for index, item in enumerate(generated)
                  if item.validation_status == "failed"]
        if not failed:
            break
        if time.monotonic() >= deadline:
            for index, _item in failed:
                provider_errors[_TIERS[index][0]] = 'TIMEOUT'
            break
        for index, candidate in request_round([(index, validation_reason(item)) for index, item in failed]):
            if candidate is not None:
                generated[index] = candidate
        generated = validate_variations(generated)
    warnings = []
    for item in generated:
        if item.validation_status == "failed":
            warnings.append(f"{item.tier} 梯次经最多 3 轮生成仍未通过校验，需人工复核：{item.reason or '生成失败'}")
    return {"questions": generated, "warnings": warnings, "failure_codes": {
        item.tier: provider_errors.get(item.tier, "PARSE_FAILED")
        for item in generated if item.validation_status == "failed"
    }}
