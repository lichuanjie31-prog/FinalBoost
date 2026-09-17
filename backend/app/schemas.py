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
    # 最终模拟判卷不带图片；普通图片判卷必须至少 1 张（在 validator 里区分）
    fileIds: list[str] = Field(default_factory=list, max_length=10)
    paperId: str | None = None
    mockExamId: str | None = None
    @model_validator(mode="after")
    def valid(self):
        if self.mockExamId:
            if self.fileIds: raise ValueError("fileIds must be empty when mockExamId is set")
        elif len(self.fileIds) < 1: raise ValueError("fileIds must contain at least 1 item")
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


# ─────────────────────────────────────────────────────────────────────────
# 最终模拟（mock exam）相关模型 —— 对应 API 文档 v1.0 第 15 节
# 注意：返回给前端的题目结构**不包含** correctAnswer，避免学生拿到答案
# ─────────────────────────────────────────────────────────────────────────

class MockOption(BaseModel):
    label: str  # "A" / "B" / "C" / "D"
    text: str

class MockQuestionInternal(BaseModel):
    """题库里的原始题目（含标准答案），仅后端内部使用。"""
    questionId: str
    prompt: str
    options: list[MockOption] | None = None
    maxScore: float
    knowledgePointIds: list[str]
    knowledgePoints: list[str]
    correctAnswer: str  # 选择题是选项 label；简答题是参考答案

class MockQuestionPublic(BaseModel):
    """暴露给前端的题目（不含标准答案）。"""
    questionId: str
    prompt: str
    options: list[MockOption] | None = None
    maxScore: float
    knowledgePointIds: list[str]
    knowledgePoints: list[str]

class MockStudentAnswer(BaseModel):
    questionId: str
    answer: str
    answeredAt: float | None = None

class MockExamOut(BaseModel):
    mockExamId: str
    examId: str
    status: Literal["ready", "submitted", "graded"]
    questions: list[MockQuestionPublic]
    maxScore: float
    createdAt: float
    submittedAt: float | None = None
    gradedAt: float | None = None
    gradingId: str | None = None  # 判卷完成后回填

class MockExamSubmitIn(StrictModel):
    """学生提交作答。"""
    answers: list[MockStudentAnswer]
    @field_validator("answers")
    @classmethod
    def non_empty(cls, value):
        if not value: raise ValueError("answers must not be empty")
        ids = [a.questionId for a in value]
        if len(set(ids)) != len(ids): raise ValueError("duplicate questionIds in answers")
        return value
