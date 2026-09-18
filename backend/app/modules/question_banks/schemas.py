from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ...schemas import StrictModel


SubjectScope = Literal["system", "private"]
PaperVisibility = Literal["private", "public"]
PublicationStatus = Literal["draft", "published", "unpublished"]


class SubjectIn(StrictModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class SubjectOut(BaseModel):
    subjectId: str
    name: str
    scope: SubjectScope


class PaperSubject(BaseModel):
    subjectId: str
    name: str
    scope: SubjectScope


class PaperOut(BaseModel):
    paperId: str
    subject: PaperSubject
    name: str
    college: str
    year: int = Field(ge=1900, le=2100)
    semester: str
    visibility: PaperVisibility
    publicationStatus: PublicationStatus | None
    fileId: str
    fileName: str
    fileSize: int = Field(ge=0)
    sourcePublicPaperId: str | None
    createdAt: datetime
    publishedAt: datetime | None


class PrivatePaperOut(PaperOut):
    downloadUrl: str | None = None


class PublicPaperOut(BaseModel):
    paperId: str
    subject: PaperSubject
    name: str
    college: str
    year: int = Field(ge=1900, le=2100)
    semester: str
    publishedAt: datetime
    copied: bool
    privatePaperId: str | None


class EmptyBody(StrictModel):
    pass
