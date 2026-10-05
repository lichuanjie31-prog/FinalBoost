"""Structured marking evidence; numeric scores deliberately remain absent."""
import math
from typing import Literal
from pydantic import Field
from ..schemas import StrictModel

class MarkingInput(StrictModel):
    examId: str = Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    fileId: str = Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    referenceFileId: str | None = Field(default=None,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    # Page order is explicit: created_at ties are possible when several pages are
    # submitted back to back.
    pageIndex: int = Field(default=0,ge=0,le=99)
    requestKey: str = Field(min_length=1,max_length=128)

class MarkingAnswerOut(StrictModel):
    answerId: str
    handwriting: str
    # None means the grader did not judge this answer; it must never read as wrong.
    correct: bool | None
    analysis: str
    rightAnswer: str
    knowledgePoints: list[str]
    errorReason: str = ''
    # Self-reported and frequently absent; never invented on the model's behalf.
    confidence: float | None = None
    polygon: list[float] | None = None
    # Reserved for the future red-pen overlay. No provider is allowed to guess it
    # yet, so it is always null and the UI stays text-only.
    boundingBox: None = None
    score: None = None
    maxScore: None = None


class MarkingQuestionOut(StrictModel):
    questionId: str
    text: str
    subject: str
    questionType: str
    polygon: list[float] | None = None
    imagePolygons: list[list[float]] = []
    rightAnswer: str
    confidence: float | None = None
    boundingBox: None = None
    answers: list[MarkingAnswerOut]
    children: list['MarkingQuestionOut'] = []


class MarkingResultOut(StrictModel):
    questions: list[MarkingQuestionOut]
    angle: float
    subject: str = ''
    # No rubric is supplied to any grader, so no percentage score exists.
    totalScore: None = None
    maxScore: None = None
    coordinateSpace: Literal['provider_pixels', 'none']
    coordinateAlignmentVerified: bool
    scoreStatus: Literal['unavailable']
    notice: str


MarkingQuestionOut.model_rebuild()


class MarkingErrorOut(StrictModel):
    """Machine code plus a user-facing explanation. Never carries raw vendor text."""
    code: str
    message: str


class MarkingOutput(StrictModel):
    jobId: str
    examId: str
    status: Literal['submitting','submission_unknown','queued','running','succeeded','failed']
    # `source` is the provider that produced this job: qwen | tencent.
    source: Literal['qwen','tencent'] = 'tencent'
    model: str | None = None
    pageIndex: int = 0
    providerJobId: str | None = None
    image: dict
    result: MarkingResultOut | None = None
    # The vendor's own response, kept verbatim for reconciliation and later AI use.
    # Only returned for a single job, never in the list projection.
    raw: dict | None = None
    error: MarkingErrorOut | None = None
    requestId: str | None = None
    queryRequestId: str | None = None
    # Token accounting for cost analysis. Never contains the API key.
    usage: dict | None = None
    latencyMs: float | None = None
    createdAt: float = 0
    retryAfterSeconds: float = 6

class MarkingReadiness(StrictModel):
    ready: bool
    mode: Literal['disabled','fixture','live']
    provider: Literal['qwen','tencent'] = 'qwen'
    model: str | None = None
    reason: str | None = None
    message: str
    region: str | None = None
    submitIntervalSeconds: float | None = None

class MarkingPage(StrictModel):
    items: list[MarkingOutput]
    nextCursor: str | None = None


def polygon(value):
    if not isinstance(value,list) or len(value)!=8: return None
    if any(type(v) not in (float,int) or not math.isfinite(v) or v<0 for v in value): return None
    return value


def image_polygons(item):
    """QuestionImagePositions is a list of Positions objects, each wrapping an 8-point list."""
    result=[]
    for entry in item.get('QuestionImagePositions') or []:
        candidate=polygon(entry.get('Position')) if isinstance(entry,dict) else None
        if candidate: result.append(candidate)
    return result


def normalize_result(raw):
    if raw.get('JobStatus')!='DONE': raise ValueError('批改尚未完成')
    count=0
    def question(item, path, depth=0):
        nonlocal count
        if depth>16: raise ValueError('题目嵌套过深')
        answers=[]
        for index,a in enumerate(item.get('AnswerInfos') or []):
            count+=1
            if count>2000: raise ValueError('批改结果过大')
            correct=a.get('IsCorrect')
            answers.append({'answerId':f'{path}.a{index+1}', 'handwriting':a.get('HandwriteInfo') or '',
                # A missing IsCorrect stays undetermined; it is never counted as wrong.
                'correct':correct if type(correct) is bool else None,
                'analysis':a.get('AnswerAnalysis') or '', 'rightAnswer':a.get('RightAnswer') or '',
                'knowledgePoints':a.get('KnowledgePoints') or [], 'polygon':polygon(a.get('HandwriteInfoPositions')),
                'errorReason':'', 'confidence':None, 'boundingBox':None,
                'score':None,'maxScore':None})
        return {'questionId':path,'text':item.get('MarkItemTitle') or '',
            'subject':item.get('Subject') or '', 'questionType':item.get('QuestionType') or '',
            'polygon':polygon(item.get('QuestionPositions')),'imagePolygons':image_polygons(item),
            'rightAnswer':item.get('RightAnswer') or '',
            'confidence':None,'boundingBox':None,
            'answers':answers,'children':[question(q,f'{path}.{i+1}',depth+1) for i,q in enumerate(item.get('MarkInfos') or [])]}
    questions=[question(q,str(i+1)) for i,q in enumerate(raw.get('MarkInfos') or [])]
    if not questions or count==0: raise ValueError('没有可用的逐题批改结果，请核对图片内容')
    angle=raw.get('Angle') or 0
    if type(angle) not in (float,int) or not math.isfinite(angle): raise ValueError('无效旋转角度')
    return {'questions':questions,'angle':angle,'subject':'','totalScore':None,'maxScore':None,
        'coordinateSpace':'provider_pixels','coordinateAlignmentVerified':False,
        'scoreStatus':'unavailable','notice':'AI 批改需核对；缺少评分细则，未计算分数。坐标需结合旋转角度验证后叠加。'}


# --------------------------------------------------------------------------
# Qwen VL normalization
# --------------------------------------------------------------------------

QWEN_NOTICE = ('AI 批改结果以文字形式展示，原卷坐标批注仍在测试中。'
               '缺少评分细则，未计算百分制分数；请核对识别内容后再据以复习。')

MAX_KNOWLEDGE_POINTS = 5
MAX_QWEN_QUESTIONS = 500


def _text(value):
    """Coerce a model-supplied scalar to trimmed text; anything else becomes ''."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool) or value is None:
        return ''
    if isinstance(value, (int, float)):
        return str(value)
    return ''


def _confidence(value):
    """Clamp to 0..1. A missing or non-finite value stays None rather than guessed."""
    if isinstance(value, bool) or type(value) not in (int, float):
        return None
    if not math.isfinite(value):
        return None
    return min(1.0, max(0.0, float(value)))


def qwen_judgement(value, *, has_stem, has_answer):
    """Map the model's judgement onto the tri-state `correct`.

    Only an explicit correct/incorrect is honoured, and only when the model
    actually reported both a stem and the student's answer. Everything else is
    undetermined — never wrong — so an unreadable page can never be silently
    graded as incorrect.
    """
    if not (has_stem and has_answer):
        return None
    if value == 'correct':
        return True
    if value == 'incorrect':
        return False
    return None


def normalize_qwen_result(payload):
    if not isinstance(payload, dict):
        raise ValueError('批改结果结构无效')
    raw_questions = payload.get('questions')
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError('视觉多模态模型未识别出任何题目，请确认图片清晰且包含题目')
    count = 0
    substantive = 0

    def question(item, path, depth=0):
        nonlocal count, substantive
        if not isinstance(item, dict):
            raise ValueError('题目结构无效')
        if depth > 16:
            raise ValueError('题目嵌套过深')
        count += 1
        if count > MAX_QWEN_QUESTIONS:
            raise ValueError('题目数量异常')
        text = _text(item.get('question_text'))
        student = _text(item.get('student_answer'))
        right = _text(item.get('correct_answer'))
        if text or student or right:
            substantive += 1
        confidence = _confidence(item.get('confidence'))
        correct = qwen_judgement(item.get('judgement'), has_stem=bool(text), has_answer=bool(student))
        points = [_text(p) for p in (item.get('knowledge_points') or []) if _text(p)]
        answers = [{
            'answerId': f'{path}.a1',
            'handwriting': student,
            'correct': correct,
            'analysis': _text(item.get('analysis')),
            'rightAnswer': right,
            'knowledgePoints': points[:MAX_KNOWLEDGE_POINTS],
            # An error reason is only meaningful once we are sure the answer is wrong.
            'errorReason': _text(item.get('error_reason')) if correct is False else '',
            'confidence': confidence,
            'polygon': None,
            'boundingBox': None,
            'score': None, 'maxScore': None,
        }]
        return {
            'questionId': path, 'text': text, 'subject': '', 'questionType': _text(item.get('question_type')),
            'polygon': None, 'imagePolygons': [], 'rightAnswer': right,
            'confidence': confidence, 'boundingBox': None,
            'answers': answers,
            'children': [question(child, f'{path}.{i+1}', depth+1)
                         for i, child in enumerate(item.get('children') or [])],
        }

    questions = [question(item, str(i+1)) for i, item in enumerate(raw_questions)]
    if not substantive:
        raise ValueError('视觉多模态模型返回的题目内容为空，未生成分数')
    return {'questions': questions, 'angle': 0, 'subject': _text(payload.get('subject')),
        'totalScore': None, 'maxScore': None,
        'coordinateSpace': 'none', 'coordinateAlignmentVerified': False,
        'scoreStatus': 'unavailable', 'notice': QWEN_NOTICE}
