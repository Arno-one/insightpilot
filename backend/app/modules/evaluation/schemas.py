from typing import Literal

from pydantic import BaseModel, Field


EvaluationTargetType = Literal["agent", "tool", "rag", "nl2sql"]


class EvaluationDatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=4000)
    target_type: EvaluationTargetType = "agent"
    metadata_json: dict | None = None


class EvaluationCaseCreateRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=160)
    user_input: str = Field(..., min_length=1, max_length=12000)
    expected_behavior: str = Field(..., min_length=1, max_length=12000)
    target_type: EvaluationTargetType = "agent"
    target_name: str = Field(..., min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata_json: dict | None = None
