"""Request/response models for the API contract (TASK 9)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=20000)

    @field_validator("session_id", "message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v


class Citation(BaseModel):
    doc_id: str
    locator: str


class ToolCall(BaseModel):
    name: str
    args: dict
    status: Literal["pending_confirmation", "success", "error"]


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    route: Literal["rag", "tool", "hybrid", "clarify", "no_answer", "refuse"]
    citations: list[Citation]
    tool_calls: list[ToolCall]
    pending_confirmation: bool
