from typing import Literal

from pydantic import BaseModel, Field


class NL2SQLSessionCreateRequest(BaseModel):
    title: str | None = Field(None, max_length=120)
    data_scope: Literal["self", "team", "all"] = "self"
    context_json: dict | None = None


class NL2SQLMessageCreateRequest(BaseModel):
    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: str = Field(..., min_length=1, max_length=12000)
    query_id: str | None = Field(None, max_length=64)
    metadata_json: dict | None = None


class NL2SQLQueryAuditCreateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    question: str = Field(..., min_length=1, max_length=4000)


class NL2SQLQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = Field(None, max_length=64)
