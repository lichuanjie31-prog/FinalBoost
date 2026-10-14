"""Stable internal topic identifiers for high-school science diagnostics.

These identifiers are an application taxonomy, not government-issued codes.
Specific combined-model tags take precedence over their broader context.
"""
import re
import hashlib


KNOWLEDGE_TAXONOMY = (
    ('PHYS-MOM-01', '动量守恒', ('动量', '碰撞', '反冲')),
    ('PHYS-EM-02', '电磁感应与导体棒模型', ('电磁感应', '导体棒', '楞次', '法拉第')),
    ('PHYS-NEWTON-01', '牛顿运动定律', ('牛顿', '受力分析', '动力学')),
    ('PHYS-ENERGY-01', '机械能与功', ('机械能', '动能', '功能关系', '功和能')),
    ('PHYS-MOTION-01', '运动学', ('运动学', '匀变速', '抛体', '自由落体')),
    ('PHYS-ELEC-01', '电场与电路', ('电场', '电路', '电势', '欧姆')),
    ('MATH-DERIV-02', '导数应用', ('导数', '微分')),
    ('MATH-TRIG-01', '三角恒等变换', ('三角恒等', '三角函数', '正弦', '余弦')),
    ('MATH-SOLID-01', '立体几何', ('立体几何', '空间几何', '空间向量', '二面角')),
    ('MATH-ANALYTIC-01', '解析几何', ('解析几何', '圆锥曲线', '椭圆', '双曲线', '抛物线')),
    ('MATH-FUNC-01', '函数性质', ('函数', '单调性', '奇偶性', '周期性')),
    ('MATH-ALG-01', '代数方程与运算', ('方程', '整式', '代数', '不等式')),
    ('MATH-PROB-01', '概率与统计', ('概率', '统计', '分布', '排列组合')),
    ('MATH-SEQ-01', '数列', ('数列', '等差', '等比')),
    ('CHEM-REACTION-01', '化学反应原理', ('化学反应', '化学平衡', '反应速率')),
    ('CHEM-ORGANIC-01', '有机化学', ('有机', '烃', '酯化')),
    ('BIO-GENETICS-01', '遗传与变异', ('遗传', '变异', '基因')),
    ('BIO-CELL-01', '细胞与代谢', ('细胞', '代谢', '光合作用', '呼吸作用')),
)


def map_to_standard_code(raw_tag: str) -> tuple[str, str]:
    name = str(raw_tag).strip()
    normalized = re.sub(r'\s+', '', name)
    for code, standard, keywords in KNOWLEDGE_TAXONOMY:
        if normalized == code or any(keyword in normalized for keyword in keywords):
            return code, standard
    # Preserve unknown tags while giving them stable, collision-resistant keys.
    return 'CUSTOM-' + hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16].upper(), name


def normalize_answer_structure(question):
    """Accept nested marking evidence or DuMate's explicit flat answer fields."""
    if not isinstance(question, dict):
        raise ValueError('题目结构无效')
    if 'answers' in question:
        answers = question['answers']
        if answers is None:
            return []
        if not isinstance(answers, list) or any(not isinstance(item, dict) for item in answers):
            raise ValueError('作答结构无效')
        return answers
    if any(key in question for key in ('correct', 'is_correct', 'judgement', 'verdict')):
        value = next((question[key] for key in ('correct', 'is_correct', 'judgement', 'verdict')
                      if key in question), None)
        correct = value if type(value) is bool else {'correct': True, 'incorrect': False,
                                                   'wrong': False}.get(str(value))
        return [dict(question, correct=correct,
                     knowledgePoints=question.get('knowledgePoints', question.get('knowledge_points', [])),
                     errorReason=question.get('errorReason', question.get('error_reason', '')))]
    return []
