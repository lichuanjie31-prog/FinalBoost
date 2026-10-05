"""薄弱点聚类：纯计算端点，不读数据库、不调用任何大模型。

输入是 N4 归一化后的批改结果（MarkingResultOut），按知识点聚合错题并排序。
判定口径与 normalize_qwen_result 的三态一致：只有 correct == False 才算错，
correct == None（未判定）既不进分子也不进分母。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from .common import envelope, fail
from .service_auth import service_token_guard

router = APIRouter(prefix='/api/v1/analysis', tags=['analysis'])

WEAK_THRESHOLD = 0.8
MAX_QUESTIONS = 500


class WeakPointIn(BaseModel):
    """归一化后的批改结果；questions 即 MarkingResultOut.questions。"""
    model_config = ConfigDict(extra="allow")
    questions: list[dict] = []
    threshold: float = WEAK_THRESHOLD


def collect_weak_points(questions, threshold):
    stats = {}
    for index, question in enumerate(questions, 1):
        question_id = str(question.get('questionId') or index)
        for answer in question.get('answers') or []:
            correct = answer.get('correct')
            # 未判定既不算对也不算错：不进入任何分母，避免把识别失败当成薄弱点。
            if correct is None:
                continue
            for point in answer.get('knowledgePoints') or []:
                name = str(point).strip()
                if not name:
                    continue
                bucket = stats.setdefault(name, {'correct': 0, 'wrong': 0, 'questionIds': []})
                if correct is True:
                    bucket['correct'] += 1
                else:
                    bucket['wrong'] += 1
                    if question_id not in bucket['questionIds']:
                        bucket['questionIds'].append(question_id)

    weak = []
    for name, bucket in stats.items():
        total = bucket['correct'] + bucket['wrong']
        if total == 0:
            continue
        accuracy = bucket['correct'] / total
        if accuracy < threshold:
            weak.append({
                'knowledgePoint': name,
                'wrongCount': bucket['wrong'],
                'correctCount': bucket['correct'],
                'accuracy': round(accuracy, 4),
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
