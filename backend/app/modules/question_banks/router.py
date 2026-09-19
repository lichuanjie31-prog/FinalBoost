from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import FileResponse

from ...auth import current_user, require_admin
from ...schemas import Envelope, Page
from .schemas import (
    EmptyBody,
    PaperOut,
    PaperVisibility,
    PrivatePaperSummaryOut,
    PrivatePaperOut,
    PublicationStatus,
    PublicPaperOut,
    SubjectIn,
    SubjectOut,
)
from . import service


router = APIRouter(
    prefix="/api/v1",
    tags=["question-banks"],
)

IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]


@router.get("/subjects", response_model=Envelope[Page[SubjectOut]])
def list_subjects(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(current_user),
):
    return service.list_subjects(request, user, q, cursor, limit)


@router.post(
    "/subjects/private",
    response_model=Envelope[SubjectOut],
    status_code=201,
)
def create_private_subject(request: Request, body: SubjectIn, idempotency_key: IdempotencyKey, user=Depends(current_user)):
    return service.create_subject(request, user, body.name, "private")


@router.post(
    "/subjects/system",
    response_model=Envelope[SubjectOut],
    status_code=201,
)
def create_system_subject(request: Request, body: SubjectIn, idempotency_key: IdempotencyKey, user=Depends(require_admin)):
    return service.create_subject(request, user, body.name, "system")


@router.post(
    "/papers",
    response_model=Envelope[PaperOut],
    status_code=201,
)
def upload_paper(
    request: Request,
    idempotency_key: IdempotencyKey,
    file: UploadFile = File(...),
    subject_id: str = Form(alias="subjectId"),
    name: str = Form(min_length=1, max_length=200),
    college: str = Form(min_length=1, max_length=100),
    year: int = Form(ge=1900, le=2100),
    semester: str = Form(min_length=1, max_length=30),
    visibility: PaperVisibility = Form(),
    user=Depends(current_user),
):
    return service.upload_paper(request, user, file, subject_id, name, college, year, semester, visibility)


@router.get("/papers/private", response_model=Envelope[Page[PrivatePaperSummaryOut]])
def list_private_papers(
    request: Request,
    subject_id: str | None = Query(default=None, alias="subjectId"),
    q: str | None = Query(default=None, max_length=200),
    year: int | None = Query(default=None, ge=1900, le=2100),
    semester: str | None = Query(default=None, max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(current_user),
):
    return service.list_private_papers(request, user, subject_id, q, year, semester, cursor, limit)


@router.get("/papers/private/{paper_id}", response_model=Envelope[PrivatePaperOut])
def get_private_paper(paper_id: str, request: Request, user=Depends(current_user)):
    return service.private_paper(request, user, paper_id)


@router.get(
    "/papers/private/{paper_id}/file",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Owned XLSX file",
        },
    },
)
def download_private_paper(paper_id: str, request: Request, user=Depends(current_user)):
    path, name = service.downloadable_private(request, user, paper_id)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=name, headers={"Cache-Control":"private, no-store", "X-Content-Type-Options":"nosniff"})


@router.get("/admin/papers", response_model=Envelope[Page[PaperOut]])
def list_admin_papers(
    request: Request,
    status: PublicationStatus | None = None,
    subject_id: str | None = Query(default=None, alias="subjectId"),
    q: str | None = Query(default=None, max_length=200),
    year: int | None = Query(default=None, ge=1900, le=2100),
    semester: str | None = Query(default=None, max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(require_admin),
):
    return service.list_admin_papers(request, user, status, subject_id, q, year, semester, cursor, limit)


@router.get("/admin/papers/{paper_id}", response_model=Envelope[PaperOut])
def get_admin_paper(paper_id: str, request: Request, user=Depends(require_admin)):
    return service.admin_paper(request, user, paper_id)


@router.get(
    "/admin/papers/{paper_id}/file",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Administrator-owned source XLSX file",
        },
    },
)
def download_admin_paper(paper_id: str, request: Request, user=Depends(require_admin)):
    path, name = service.downloadable_admin(request, user, paper_id)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=name, headers={"Cache-Control":"private, no-store", "X-Content-Type-Options":"nosniff"})


@router.post(
    "/admin/papers/{paper_id}/publish",
    response_model=Envelope[PaperOut],
)
def publish_paper(paper_id: str, request: Request, body: EmptyBody, idempotency_key: IdempotencyKey, user=Depends(require_admin)):
    return service.change_publication(request, user, paper_id, "published")


@router.post(
    "/admin/papers/{paper_id}/unpublish",
    response_model=Envelope[PaperOut],
)
def unpublish_paper(paper_id: str, request: Request, body: EmptyBody, idempotency_key: IdempotencyKey, user=Depends(require_admin)):
    return service.change_publication(request, user, paper_id, "unpublished")


@router.get("/public/papers", response_model=Envelope[Page[PublicPaperOut]])
def list_public_papers(
    request: Request,
    subject_id: str | None = Query(default=None, alias="subjectId"),
    college: str | None = Query(default=None, max_length=100),
    year: int | None = Query(default=None, ge=1900, le=2100),
    semester: str | None = Query(default=None, max_length=30),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(current_user),
):
    return service.list_public_papers(request, user, subject_id, college, year, semester, q, cursor, limit)


@router.post(
    "/public/papers/{paper_id}/copy",
    response_model=Envelope[PrivatePaperOut],
    status_code=201,
)
def copy_public_paper(
    paper_id: str,
    request: Request,
    body: EmptyBody,
    idempotency_key: IdempotencyKey,
    user=Depends(current_user),
):
    return service.copy_public_paper(request, user, paper_id)
