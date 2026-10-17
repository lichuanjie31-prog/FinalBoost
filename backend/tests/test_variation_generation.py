import json

from app.services.variation_questions import generate_variation_questions


class SequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return type("Response", (), {"content": value})()


def payload(tier, stem, analysis="最终答案：2"):
    return json.dumps({
        "tier": tier,
        "source_knowledge_point": "一元一次方程",
        "difficulty": "easy",
        "stem": stem,
        "options": None,
        "answer": "2",
        "analysis": analysis,
    }, ensure_ascii=False)


def test_generates_all_three_tiers_with_shared_contract():
    model = SequenceModel([
        payload("consolidation", "解方程 x+1=3"),
        payload("reverse", "已知方程的解为 2，求方程右侧常数"),
        payload("extension", "方程应用：小明有 x 个苹果，增加 2 个后为 4 个，求 x"),
    ])

    result = generate_variation_questions(model, "解方程 x+1=3", "一元一次方程")

    assert [item.tier for item in result["questions"]] == ["consolidation", "reverse", "extension"]
    assert all(item.validation_status == "passed" for item in result["questions"])
    assert len(model.prompts) == 3


def test_failed_validation_gets_two_targeted_retries_then_warning():
    model = SequenceModel([
        payload("consolidation", "解方程 x+1=3"),
        payload("reverse", "计算三角形面积"),
        payload("extension", "求函数 y=sin(x) 的最大值"),
        payload("reverse", "计算圆的周长"),
        payload("extension", "求函数 y=cos(x) 的最大值"),
        payload("reverse", "计算三角形周长"),
        payload("extension", "求三角函数周期"),
    ])

    result = generate_variation_questions(model, "解方程 x+1=3", "一元一次方程")

    assert result["questions"][1].validation_status == "failed"
    assert any(warning.startswith("reverse ") for warning in result["warnings"])
    assert len(model.prompts) == 7


def test_targeted_retry_can_repair_drift_and_clear_warning():
    model = SequenceModel([
        payload("consolidation", "解方程 x+1=3"),
        payload("reverse", "计算三角形面积"),
        payload("extension", "一元一次方程应用：已知 x=2，求 x+1"),
        payload("reverse", "已知一元一次方程的解为 2，求另一个方程的系数"),
    ])

    result = generate_variation_questions(model, "解方程 x+1=3", "一元一次方程")

    assert result["questions"][1].validation_status == "passed"
    assert result["warnings"] == []
    assert len(model.prompts) == 4
    assert "针对上次校验问题修正" in model.prompts[3]


def test_invalid_model_json_retries_once_and_stays_failed():
    model = SequenceModel([
        "{}", payload("reverse", "一元一次方程的解已知为 2，求方程右侧常数"),
        payload("extension", "一元一次方程应用：已知 x=2，求 x+1"), "{}",
    ])

    result = generate_variation_questions(model, "解方程 x+1=3", "一元一次方程")

    assert result["questions"][0].validation_status == "failed"
    assert any(warning.startswith("consolidation ") for warning in result["warnings"])


def test_provider_failure_is_retried_and_reported_without_fabrication():
    model = SequenceModel([
        RuntimeError("offline"), RuntimeError("offline"),
    ])

    result = generate_variation_questions(model, "解方程 x+1=3", "一元一次方程")

    assert result["questions"][0].validation_status == "failed"
    assert any(warning.startswith("consolidation ") for warning in result["warnings"])


def test_missing_model_does_not_fabricate_questions():
    result = generate_variation_questions(None, "解方程 x+1=3", "一元一次方程")

    assert result["questions"] == []
    assert result["warnings"]
