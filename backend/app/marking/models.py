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
    # None means the vendor did not judge this answer; it must never read as wrong.
    correct: bool | None
    analysis: str
    rightAnswer: str
    knowledgePoints: list[str]
    polygon: list[float] | None = None
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
    answers: list[MarkingAnswerOut]
    children: list['MarkingQuestionOut'] = []


class MarkingResultOut(StrictModel):
    questions: list[MarkingQuestionOut]
    angle: float
    # No rubric is supplied to the vendor, so no percentage score exists.
    totalScore: None = None
    maxScore: None = None
    coordinateSpace: Literal['provider_pixels']
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
    source: Literal['tencent'] = 'tencent'
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
    createdAt: float = 0
    retryAfterSeconds: float = 6

class MarkingReadiness(StrictModel):
    ready: bool
    mode: Literal['disabled','fixture','tencent']
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
                'score':None,'maxScore':None})
        return {'questionId':path,'text':item.get('MarkItemTitle') or '',
            'subject':item.get('Subject') or '', 'questionType':item.get('QuestionType') or '',
            'polygon':polygon(item.get('QuestionPositions')),'imagePolygons':image_polygons(item),
            'rightAnswer':item.get('RightAnswer') or '',
            'answers':answers,'children':[question(q,f'{path}.{i+1}',depth+1) for i,q in enumerate(item.get('MarkInfos') or [])]}
    questions=[question(q,str(i+1)) for i,q in enumerate(raw.get('MarkInfos') or [])]
    if not questions or count==0: raise ValueError('没有可用的逐题批改结果，请核对图片内容')
    angle=raw.get('Angle') or 0
    if type(angle) not in (float,int) or not math.isfinite(angle): raise ValueError('无效旋转角度')
    return {'questions':questions,'angle':angle,'totalScore':None,'maxScore':None,
        'coordinateSpace':'provider_pixels','coordinateAlignmentVerified':False,
        'scoreStatus':'unavailable','notice':'AI 批改需核对；缺少评分细则，未计算分数。坐标需结合旋转角度验证后叠加。'}
