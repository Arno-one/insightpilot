from pydantic import BaseModel, Field


class MemoryGovernanceActionRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)
