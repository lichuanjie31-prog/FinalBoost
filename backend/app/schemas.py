from datetime import date
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")
class ErrorEnvelope(BaseModel):
    code: int
    message: str
    data: None = None
    requestId: str

class Envelope(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T
    requestId: str

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=10, max_length=128)
    @field_validator("username", mode="before")
    @classmethod
    def normalize(cls, value): return value.strip().lower() if isinstance(value, str) else value

class UserOut(BaseModel):
    userId: str
    username: str
    role: Literal["student", "admin"] = "student"

class AuthOut(BaseModel):
    accessToken: str
    expiresIn: float
    user: UserOut

class ExamIn(StrictModel):
    course: str = Field(min_length=1, max_length=100)
    examDate: date
    targetScore: float = Field(gt=0)
    maxScore: float = Field(default=100, gt=0)
    @field_validator("course")
    @classmethod
    def course_nonempty(cls, value):
        if not value.strip(): raise ValueError("course must not be blank")
        return value.strip()
    @model_validator(mode="after")
    def valid_score(self):
        if self.targetScore > self.maxScore: raise ValueError("targetScore exceeds maxScore")
        return self

class ExamOut(BaseModel):
    examId: str
    course: str
    examDate: str
    remainingDays: int
    targetScore: float
    maxScore: float
    stage: Literal["diagnosis", "training", "mock", "completed"]

class Page(BaseModel, Generic[T]):
    items: list[T]
    nextCursor: str | None = None

class FileOut(BaseModel):
    fileId: str
    fileName: str
    mimeType: str
    size: int
    url: str

class GradingIn(StrictModel):
    examId: str
    fileIds: list[str] = Field(min_length=1, max_length=10)
    paperId: str | None = None
    mockExamId: str | None = None
    @model_validator(mode="after")
    def valid(self):
        if len(set(self.fileIds)) != len(self.fileIds): raise ValueError("duplicate fileIds")
        if self.paperId and self.mockExamId: raise ValueError("paperId and mockExamId are mutually exclusive")
        return self

class GradingAccepted(BaseModel):
    gradingId: str
    status: Literal["queued"] = "queued"

class QuestionGrade(BaseModel):
    questionId: str
    score: float | None
    maxScore: float
    correct: bool | None
    knowledgePointIds: list[str]
    knowledgePoints: list[str]
    errorType: Literal["concept_error", "method_error", "calculation_error", "missing_answer", "unrecognized"] | None
    errorReason: str | None

class GradingResult(BaseModel):
    totalScore: float | None
    maxScore: float
    questions: list[QuestionGrade]

class JobError(BaseModel):
    code: int
    message: str

class GradingOut(BaseModel):
    gradingId: str
    examId: str
    status: Literal["queued", "running", "succeeded", "failed"]
    result: GradingResult | None
    error: JobError | None
    source: Literal["mock", "provider"]

class DiagnosisIn(StrictModel):
    gradingId: str

class OutlineItem(BaseModel):
    knowledgePointId: str
    knowledgePoint: str
    mastery: float | None
    scoreRate: float

class WeakPoint(BaseModel):
    knowledgePointId: str
    name: str

class DiagnosisOut(BaseModel):
    diagnosisId: str
    estimatedScore: float
    outline: list[OutlineItem]
    weakPoints: list[WeakPoint]
    source: Literal["mock", "provider"]

StageType = Literal["method", "guided", "easy", "medium", "quiz"]
StageStatus = Literal["locked", "unlocked", "completed"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]

class TrainingIn(StrictModel):
    examId: str
    knowledgePointId: str
    targetMastery: float = Field(default=80, gt=0, le=100)

class TrainingStage(BaseModel):
    type: StageType
    title: str
    status: StageStatus

class TrainingOut(BaseModel):
    trainingId: str
    title: str
    currentMastery: float | None
    targetMastery: float
    estimatedScoreGain: float | None
    stages: list[TrainingStage]

class QuestionOption(BaseModel):
    key: str
    text: str

class QuestionOut(BaseModel):
    questionId: str
    course: str
    year: int | None = None
    paperId: str | None = None
    paper: str | None = None
    content: str
    imageFileIds: list[str] = Field(default_factory=list)
    options: list[QuestionOption] = Field(default_factory=list)
    knowledgePointIds: list[str] = Field(default_factory=list)
    difficulty: int = Field(ge=1, le=5)
    score: float
    sourceType: Literal["real_exam", "similar_exam", "ai_variant"]

class StageOut(BaseModel):
    type: StageType
    status: StageStatus
    content: str | None
    questions: list[QuestionOut]

class StageCompleteIn(StrictModel):
    pass

class StageCompleteOut(BaseModel):
    type: StageType
    status: StageStatus
    nextStageType: StageType | None

class AttemptIn(StrictModel):
    questionId: str
    answer: str | None = Field(default=None, min_length=1, max_length=10000)
    fileIds: list[str] | None = Field(default=None, min_length=1, max_length=10)
    durationSeconds: int = Field(ge=0)
    @model_validator(mode="after")
    def valid(self):
        if (self.answer is None) == (self.fileIds is None): raise ValueError("answer and fileIds are mutually exclusive and one is required")
        if self.fileIds is not None and len(set(self.fileIds)) != len(self.fileIds): raise ValueError("duplicate fileIds")
        return self

class AttemptAccepted(BaseModel):
    attemptId: str
    status: Literal["queued"] = "queued"

class AttemptResult(BaseModel):
    score: float
    maxScore: float
    correct: bool
    analysis: str
    masteryBefore: float | None
    masteryAfter: float | None

class AttemptOut(BaseModel):
    attemptId: str
    status: JobStatus
    result: AttemptResult | None
    error: JobError | None

class QuizOut(BaseModel):
    quizId: str
    question: str
    type: str

class QuizAnswerIn(StrictModel):
    quizId: str
    answer: str = Field(min_length=1, max_length=10000)

class QuizAnswerOut(BaseModel):
    quizId: str
    score: float
    conceptCorrect: bool
    missingPoints: list[str]
    masteryAfter: float | None
    passed: bool

class ExportIn(StrictModel):
    includeAnswers: bool = False
    includeAnalysis: bool = False
    @model_validator(mode="after")
    def valid(self):
        if self.includeAnalysis and not self.includeAnswers: raise ValueError("includeAnalysis requires includeAnswers")
        return self

class ExportAccepted(BaseModel):
    exportId: str
    status: Literal["queued"] = "queued"

class ExportResult(BaseModel):
    fileId: str
    fileName: str
    downloadUrl: str

class ExportOut(BaseModel):
    exportId: str
    status: JobStatus
    result: ExportResult | None
    error: JobError | None
