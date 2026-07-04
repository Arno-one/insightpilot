from typing import Literal

from pydantic import BaseModel, Field


class AgentDefinitionCreateRequest(BaseModel):
    agent_code: str = Field(..., min_length=1, max_length=80)
    agent_name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=1000)
    agent_type: str = Field("custom", min_length=1, max_length=50)
    runtime_type: Literal["chat", "workflow", "tool_agent"] = "chat"
    status: Literal["draft", "active", "disabled"] = "draft"
    version: int = Field(1, ge=1, le=9999)
    config_json: dict | None = None
    tool_policy_json: dict | None = None
    memory_policy_json: dict | None = None


class AgentDefinitionCloneRequest(BaseModel):
    version: int | None = Field(None, ge=1, le=9999)
    status: Literal["draft", "active", "disabled"] = "draft"
    agent_name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=1000)
    config_json: dict | None = None
    tool_policy_json: dict | None = None
    memory_policy_json: dict | None = None


class AgentDefinitionStatusRequest(BaseModel):
    status: Literal["draft", "active", "disabled"]
