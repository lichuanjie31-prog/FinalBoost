from __future__ import annotations
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    sessionId: str | None = None
    course: str | None = None
    examId: str | None = None
    gradingId: str | None = None


class ToolCallOut(BaseModel):
    id: str
    name: str
    arguments: dict
    result: str | None = None


class ChatResponse(BaseModel):
    sessionId: str
    message: str
    toolCalls: list[ToolCallOut] = []


class SessionCreate(BaseModel):
    course: str | None = None


class SessionOut(BaseModel):
    sessionId: str
    title: str
    course: str | None
    createdAt: float
    updatedAt: float
    lastMessage: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str | None
    toolCalls: list[ToolCallOut] = []
    toolCallId: str | None = None
    name: str | None = None
    createdAt: float