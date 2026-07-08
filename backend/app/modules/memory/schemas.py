from pydantic import BaseModel, Field


class MemoryGovernanceActionRequest(BaseModel):
    reason: str | None = Field(None, max_length=500)


class LongTermMemorySearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(12, ge=1, le=30)
    memory_types: list[str] | None = None
    include_summary: bool = True
    max_chars: int | None = Field(1200, ge=300, le=6000)
