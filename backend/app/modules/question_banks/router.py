from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse

from ...auth import current_user
from ...common import fail
from ...schemas import Envelope, ErrorEnvelope, Page
from .schemas import (
    EmptyBody,
    PaperOut,
    PaperVisibility,
    PrivatePaperOut,
    PublicationStatus,
    PublicPaperOut,
    SubjectIn,
    SubjectOut,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["question-banks"],
    dependencies=[Depends(current_user)],
)

IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]


def not_implemented() -> NoReturn:
    fail(501, "题库契约已定义，业务实现尚未接入")


@router.get("/subjects", response_model=Envelope[Page[SubjectOut]])
def list_subjects(
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    not_implemented()


@router.post(
    "/subjects/private",
    response_model=Envelope[SubjectOut],
    status_code=201,
    responses={501: {"model": ErrorEnvelope}},
)
def create_private_subject(body: SubjectIn, idempotency_key: IdempotencyKey):
    not_implemented()


@router.post(
    "/subjects/system",
    response_model=Envelope[SubjectOut],
    status_code=201,
    responses={501: {"model": ErrorEnvelope}},
)
def create_system_subject(body: SubjectIn, idempotency_key: IdempotencyKey):
    not_implemented()


@router.post(
    "/papers",
    response_model=Envelope[PaperOut],
    status_code=201,
    responses={501: {"model": ErrorEnvelope}},
)
def upload_paper(
    idempotency_key: IdempotencyKey,
    file: UploadFile = File(...),
    subject_id: str = Form(alias="subjectId"),
    name: str = Form(min_length=1, max_length=200),
    college: str = Form(min_length=1, max_length=100),
    year: int = Form(ge=1900, le=2100),
    semester: str = Form(min_length=1, max_length=30),
    visibility: PaperVisibility = Form(),
):
    not_implemented()


@router.get("/papers/private", response_model=Envelope[Page[PrivatePaperOut]])
def list_private_papers(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    q: str | None = Query(default=None, max_length=200),
    year: int | None = Query(default=None, ge=1900, le=2100),
    semester: str | None = Query(default=None, max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    not_implemented()


@router.get("/papers/private/{paper_id}", response_model=Envelope[PrivatePaperOut])
def get_private_paper(paper_id: str):
    not_implemented()


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
        501: {"model": ErrorEnvelope},
    },
)
def download_private_paper(paper_id: str):
    not_implemented()


@router.get("/admin/papers", response_model=Envelope[Page[PaperOut]])
def list_admin_papers(
    status: PublicationStatus | None = None,
    subject_id: str | None = Query(default=None, alias="subjectId"),
    q: str | None = Query(default=None, max_length=200),
    year: int | None = Query(default=None, ge=1900, le=2100),
    semester: str | None = Query(default=None, max_length=30),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    not_implemented()


@router.get("/admin/papers/{paper_id}", response_model=Envelope[PaperOut])
def get_admin_paper(paper_id: str):
    not_implemented()


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
        501: {"model": ErrorEnvelope},
    },
)
def download_admin_paper(paper_id: str):
    not_implemented()


@router.post(
    "/admin/papers/{paper_id}/publish",
    response_model=Envelope[PaperOut],
    responses={501: {"model": ErrorEnvelope}},
)
def publish_paper(paper_id: str, body: EmptyBody, idempotency_key: IdempotencyKey):
    not_implemented()


@router.post(
    "/admin/papers/{paper_id}/unpublish",
    response_model=Envelope[PaperOut],
    responses={501: {"model": ErrorEnvelope}},
)
def unpublish_paper(paper_id: str, body: EmptyBody, idempotency_key: IdempotencyKey):
    not_implemented()


@router.get("/public/papers", response_model=Envelope[Page[PublicPaperOut]])
def list_public_papers(
    subject_id: str | None = Query(default=None, alias="subjectId"),
    college: str | None = Query(default=None, max_length=100),
    year: int | None = Query(default=None, ge=1900, le=2100),
    semester: str | None = Query(default=None, max_length=30),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    not_implemented()


@router.post(
    "/public/papers/{paper_id}/copy",
    response_model=Envelope[PrivatePaperOut],
    status_code=201,
    responses={501: {"model": ErrorEnvelope}},
)
def copy_public_paper(
    paper_id: str,
    body: EmptyBody,
    idempotency_key: IdempotencyKey,
):
    not_implemented()
