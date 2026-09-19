from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from ..auth import current_user
from ..common import envelope
from ..schemas import Envelope
from .models import MarkingInput, MarkingOutput, MarkingPage, MarkingReadiness
from .service import ExamMarkingTool

router = APIRouter(prefix='/api/v1/marking', tags=['marking-tools'])


def tool(request):
    return ExamMarkingTool(request.app.state.db, request.app.state.marking_provider,
                           request.app.state.settings)


@router.get('/readiness', response_model=Envelope[MarkingReadiness])
def readiness(request: Request, user=Depends(current_user)):
    """Report whether Tencent marking is usable, without echoing credentials."""
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
