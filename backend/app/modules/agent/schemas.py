from typing import Literal

from pydantic import BaseModel, Field


class RiskChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class AgentChatSessionCreateRequest(BaseModel):
    agent_scope: str = Field("general", min_length=1, max_length=50)
    intent: str = Field("unknown", min_length=1, max_length=50)
    title: str | None = Field(None, max_length=120)
    related_customer_id: str | None = Field(None, max_length=64)
    context_json: dict | None = None


class AgentChatMessageCreateRequest(BaseModel):
    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: str = Field(..., min_length=1, max_length=12000)
    intent: str | None = Field(None, max_length=50)
    tool_name: str | None = Field(None, max_length=120)
    run_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=64)
    metadata_json: dict | None = None
