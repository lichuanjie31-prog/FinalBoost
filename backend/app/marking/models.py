"""Structured marking evidence; numeric scores deliberately remain absent."""
import math
from typing import Literal
from pydantic import Field
from ..schemas import StrictModel

class MarkingInput(StrictModel):
    examId: str = Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    fileId: str = Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    referenceFileId: str | None = Field(default=None,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    requestKey: str = Field(min_length=1,max_length=128)

class MarkingOutput(StrictModel):
    jobId: str
    status: Literal['submitting','submission_unknown','queued','running','succeeded','failed']
    source: Literal['tencent'] = 'tencent'
    image: dict
    result: dict | None = None
    error: dict | None = None
    requestId: str | None = None
    retryAfterSeconds: int = 6


def polygon(value):
    if not isinstance(value,list) or len(value)!=8: return None
    if any(type(v) not in (float,int) or not math.isfinite(v) or v<0 for v in value): return None
    return value


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
                'correct':correct if type(correct) is bool else None,
                'analysis':a.get('AnswerAnalysis') or '', 'rightAnswer':a.get('RightAnswer') or '',
                'knowledgePoints':a.get('KnowledgePoints') or [], 'polygon':polygon(a.get('HandwriteInfoPositions')),
                'score':None,'maxScore':None})
        return {'questionId':path,'text':item.get('MarkItemTitle') or '',
            'polygon':polygon(item.get('QuestionPositions')),'rightAnswer':item.get('RightAnswer') or '',
            'answers':answers,'children':[question(q,f'{path}.{i+1}',depth+1) for i,q in enumerate(item.get('MarkInfos') or [])]}
    questions=[question(q,str(i+1)) for i,q in enumerate(raw.get('MarkInfos') or [])]
    if not questions or count==0: raise ValueError('没有可用的逐题批改结果，请核对图片内容')
    angle=raw.get('Angle') or 0
    if type(angle) not in (float,int) or not math.isfinite(angle): raise ValueError('无效旋转角度')
    return {'questions':questions,'angle':angle,'totalScore':None,'maxScore':None,
        'coordinateSpace':'provider_pixels','coordinateAlignmentVerified':False,
        'scoreStatus':'unavailable','notice':'AI 批改需核对；缺少评分细则，未计算分数。坐标需结合旋转角度验证后叠加。'}
