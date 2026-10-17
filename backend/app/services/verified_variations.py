"""Solver-backed variations for the auxiliary-angle method, without an LLM."""
import sympy as sp

from ..tool_contracts import VariationQuestion
from .question_validator import validate_variations


def auxiliary_angle_variations(source_question: str, knowledge_point: str):
    """Return three independently derived questions for an explicitly known method.

    This is a small verified exercise family, not an answer to the uploaded
    original question. Other topics must use their own generation pipeline.
    """
    if not any(word in knowledge_point + source_question for word in ('辅助角', '凑角')):
        return None
    if not any(word in source_question for word in ('sin', 'cos', '正弦', '余弦')):
        return None
    t = sp.Symbol('t', real=True)
    original = sp.sin(t) * sp.cos(t) + sp.sqrt(3) / 2 * sp.cos(2 * t)
    assert sp.trigsimp(sp.expand_trig(original - sp.cos(2 * t - sp.pi / 6))) == 0
    cosine = (5 - 12 * sp.sqrt(3)) / 26
    sine = sp.sqrtdenest(sp.sqrt(1 - cosine**2))
    assert cosine < 0 and sine > 0
    assert sp.simplify(sine - (12 + 5 * sp.sqrt(3)) / 26) == 0
    reverse = sp.simplify(cosine / 2 + sp.sqrt(3) * sine / 2)
    extension = 2 * sp.Rational(8, 17)**2 - 1
    references = [sp.simplify(sp.Rational(5, 13) / 2 - sp.Rational(12, 13) * sp.sqrt(3) / 2),
                  reverse, extension]
    prefix = f'【{knowledge_point}】'
    stems = [
        prefix + '同构巩固：用辅助角公式化简 F(t)=2sin(t)cos(t)+sqrt(3)cos(2t)。'
        '已知 F(x/2-pi/12)=10/13，pi/3<x<5pi/6，求 cos(x)。写明凑角和符号判断的依据。',
        prefix + '逆向检验：已知 pi/2<x<5pi/6 且 cos(x)=(5-12sqrt(3))/26。'
        '设 f(t)=sin(t)cos(t)+sqrt(3)/2*cos(2t)，求 f(x/2-pi/12)。'
        '请用辅助角公式，从已知余弦值反推出需要的复合角值。',
        prefix + '综合检验：设 h(t)=sin(t)cos(t)+sqrt(3)/2*cos(2t)，'
        'h(x/2-pi/12)=8/17，pi/3<x<5pi/6。用辅助角公式确定合适的复合角，'
        '求 cos(2x-2pi/3)，并说明怎样避免直接求出 x。',
    ]
    analyses = [
        '辅助角公式给出 F(t)=2cos(2t-pi/6)。令 delta=x-pi/3，题设变为 cos(delta)=5/13。'
        '由区间知 0<delta<pi/2，所以 sin(delta)=12/13，取正号。'
        '再用 cos(x)=cos(delta+pi/3)=cos(delta)/2-sqrt(3)sin(delta)/2。',
        '辅助角公式给出 f(t)=cos(2t-pi/6)。由 x 的区间知 sin(x)>0，'
        '所以 sin(x)=sqrt(1-cos(x)^2)=(12+5sqrt(3))/26。'
        '由凑角得到 f(x/2-pi/12)=cos(x-pi/3)=cos(x)/2+sqrt(3)sin(x)/2。',
        '辅助角公式给出 h(t)=cos(2t-pi/6)。令 delta=x-pi/3，题设为 cos(delta)=8/17。'
        '所求角恰为 2delta。用二倍角公式 cos(2delta)=2cos(delta)^2-1，'
        '代入得到 128/289-1=-161/289，无需求出角 x。',
    ]
    items = [VariationQuestion(
        tier=tier, difficulty=difficulty, source_knowledge_point=knowledge_point,
        stem=stem, answer=str(answer), analysis=analysis + f'最终答案：{answer}',
    ) for tier, difficulty, stem, answer, analysis in zip(
        ('consolidation', 'reverse', 'extension'), ('easy', 'medium', 'medium'),
        stems, references, analyses)]
    checked = validate_variations(items, verified_answers={q.stem: str(ref) for q, ref in zip(items, references)})
    if any(q.validation_status != 'passed' for q in checked):
        raise ValueError('独立验算后的三题仍未通过质量校验')
    return checked
