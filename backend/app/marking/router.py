from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from ..auth import current_user
from ..common import envelope, fail
from ..schemas import Envelope
from ..service_auth import service_token_guard
from .models import (MarkingInput, MarkingOutput, MarkingPage, MarkingReadiness,
                     MarkingResultOut, normalize_qwen_result)
from .service import ExamMarkingTool
from .symbolic import check_answer as check_symbolic_answer

router = APIRouter(prefix='/api/v1/marking', tags=['marking-tools'])


def tool(request):
    state = request.app.state
    return ExamMarkingTool(state.db, state.marking_providers, state.settings,
                           getattr(state, 'marking_executor', None))


@router.get('/readiness', response_model=Envelope[MarkingReadiness])
def readiness(request: Request, user=Depends(current_user)):
    """Report which provider is active and whether it is usable, without echoing credentials."""
    return envelope(tool(request).readiness())


@router.post('/jobs', response_model=Envelope[MarkingOutput], status_code=202)
def submit(body: MarkingInput, request: Request, user=Depends(current_user)):
    return envelope(tool(request).submit(user['id'], body))


@router.get('/jobs', response_model=Envelope[MarkingPage])
def list_jobs(request: Request, examId: str = Query(min_length=1, max_length=64),
              cursor: str | None = None, limit: int = Query(50, ge=1, le=100),
              user=Depends(current_user)):
    """List persisted page jobs for one exam so a refresh or restart can recover them."""
    return envelope(tool(request).list_by_exam(user['id'], examId, cursor, limit))


@router.get('/jobs/{job_id}', response_model=Envelope[MarkingOutput])
def get(job_id: str, request: Request, user=Depends(current_user)):
    return envelope(tool(request).get(user['id'], job_id))


@router.get('/jobs/{job_id}/image', response_class=FileResponse)
def image(job_id: str, request: Request, user=Depends(current_user)):
    return FileResponse(tool(request).image_path(user['id'], job_id), media_type='image/png',
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


class NormalizeIn(BaseModel):
    """平台模型（DuMate 原生多模态 / 百度）输出的结构化 JSON。

    字段名须与 normalize_qwen_result 对齐；多余字段一律忽略，不报错。
    """
    model_config = ConfigDict(extra="allow")
    questions: list[dict] = []
    subject: str = ""


class SymbolicAnswerIn(BaseModel):
    """A recognized final expression and an independently checked reference."""
    model_config = ConfigDict(extra="forbid")
    problem: str = Field(min_length=1, max_length=5000)
    studentAnswer: str = Field(max_length=512)
    referenceAnswer: str = Field(max_length=512)


class SymbolicAnswerOut(BaseModel):
    verdict: Literal["correct", "wrong", "uncertain"]
    reason: str


@router.post('/normalize', response_model=Envelope[MarkingResultOut])
def normalize(body: NormalizeIn, _=Depends(service_token_guard)):
    """把平台模型的视觉识别结果收敛为统一 Schema，纯规则、不调用任何大模型。"""
    try:
        result = normalize_qwen_result(body.model_dump())
    except ValueError as exc:
        fail(422, str(exc))
    return envelope(result)


@router.post('/check-answer', response_model=Envelope[SymbolicAnswerOut])
def check_answer(body: SymbolicAnswerIn, _=Depends(service_token_guard)):
    """Compare short symbolic expressions; unsupported cases remain uncertain."""
    return envelope(check_symbolic_answer(body.problem, body.studentAnswer, body.referenceAnswer))
