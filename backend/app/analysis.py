"""薄弱点聚类：纯计算端点，不读数据库、不调用任何大模型。

输入是 N4 归一化后的批改结果（MarkingResultOut），按知识点聚合错题并排序。
判定口径与 normalize_qwen_result 的三态一致：只有 correct == False 才算错，
correct == None（未判定）既不进分子也不进分母。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from .common import envelope, fail
from .service_auth import service_token_guard
from .services.knowledge_taxonomy import map_to_standard_code, normalize_answer_structure
import math

router = APIRouter(prefix='/api/v1/analysis', tags=['analysis'])

WEAK_THRESHOLD = 0.8
MAX_QUESTIONS = 500


class WeakPointIn(BaseModel):
    """归一化后的批改结果；questions 即 MarkingResultOut.questions。"""
    model_config = ConfigDict(extra="allow")
    questions: list[dict] = []
    threshold: float = WEAK_THRESHOLD


def collect_weak_points(questions, threshold):
    if not isinstance(questions, list) or not 0 <= threshold <= 1:
        raise ValueError('薄弱点参数无效')
    stats = {}
    for index, question in enumerate(questions, 1):
        answers = normalize_answer_structure(question)
        question_id = str(question.get('questionId') or question.get('question_id') or question.get('id') or index)
        for answer in answers:
            correct = answer.get('correct')
            # 未判定既不算对也不算错：不进入任何分母，避免把识别失败当成薄弱点。
            if type(correct) is not bool:
                continue
            points = answer.get('knowledgePoints', answer.get('knowledge_points', [])) or []
            if not isinstance(points, list):
                raise ValueError('考点必须为数组')
            codes = set()
            for point in points:
                name = str(point).strip()
                if not name:
                    continue
                code, standard = map_to_standard_code(name)
                if code in codes:
                    continue
                codes.add(code)
                bucket = stats.setdefault(code, {'name': standard, 'correct': 0, 'wrong': 0,
                                                'questionIds': [], 'scores': [], 'maxScores': [],
                                                'completeScores': True})
                score, max_score = answer.get('score'), answer.get('maxScore')
                scored = (type(score) in (int, float) and type(max_score) in (int, float)
                          and math.isfinite(score) and math.isfinite(max_score)
                          and 0 <= score <= max_score and max_score > 0)
                bucket['completeScores'] &= scored
                if scored:
                    bucket['scores'].append(score)
                    bucket['maxScores'].append(max_score)
                if correct is True:
                    bucket['correct'] += 1
                else:
                    bucket['wrong'] += 1
                    if question_id not in bucket['questionIds']:
                        bucket['questionIds'].append(question_id)

    weak = []
    for code, bucket in stats.items():
        total = bucket['correct'] + bucket['wrong']
        if total == 0:
            continue
        accuracy = bucket['correct'] / total
        if accuracy < threshold:
            weak.append({
                'knowledgePoint': bucket['name'],
                'code': code,
                'standardName': bucket['name'],
                'wrongCount': bucket['wrong'],
                'correctCount': bucket['correct'],
                'accuracy': round(accuracy, 4),
                'accuracyRate': round(accuracy, 4),
                'errorRate': round(1 - accuracy, 4),
                'totalScore': sum(bucket['scores']) if bucket['completeScores'] else None,
                'maxScore': sum(bucket['maxScores']) if bucket['completeScores'] else None,
                'scoreLossRate': round(1 - sum(bucket['scores']) / sum(bucket['maxScores']), 4)
                if bucket['completeScores'] else None,
                'questionIds': bucket['questionIds'],
            })
    # 最薄弱（正确率最低）排前面；同正确率时错得多的排前面。
    weak.sort(key=lambda item: (item['accuracy'], -item['wrongCount'], item['knowledgePoint']))
    return weak


@router.post('/weak-points')
def weak_points(body: WeakPointIn, _=Depends(service_token_guard)):
    if len(body.questions) > MAX_QUESTIONS:
        fail(422, '题目数量异常')
    return envelope({
        'threshold': body.threshold,
        'weakPoints': collect_weak_points(body.questions, body.threshold),
    })
