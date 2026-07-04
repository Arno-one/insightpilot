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


class NL2SQLEvaluationResultCreateRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=64)
    query_id: str | None = Field(None, max_length=64)
    generated_sql: str | None = Field(None, max_length=12000)
    status: Literal["executed", "failed"]
    row_count: int = Field(0, ge=0)
    error_message: str | None = Field(None, max_length=4000)
    elapsed_ms: int = Field(0, ge=0)
    metadata_json: dict | None = None


class RAGEvaluationResultCreateRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=64)
    trace_id: str | None = Field(None, max_length=64)
    top_k: int = Field(5, ge=1, le=50)
    hit_count: int = Field(0, ge=0)
    expected_doc_id: str | None = Field(None, max_length=128)
    expected_section_id: str | None = Field(None, max_length=128)
    matched_rank: int | None = Field(None, ge=1)
    recall_hit: bool = False
    mrr_score: float = Field(0, ge=0, le=1)
    ndcg_score: float = Field(0, ge=0, le=1)
    rerank_enabled: bool = True
    rerank_ms: int = Field(0, ge=0)
    elapsed_ms: int = Field(0, ge=0)
    metadata_json: dict | None = None


class ToolEvaluationResultCreateRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=64)
    tool_name: str = Field(..., min_length=1, max_length=120)
    run_id: str | None = Field(None, max_length=64)
    step_id: str | None = Field(None, max_length=64)
    status: Literal["success", "failed", "skipped"]
    expected_status: Literal["success", "failed", "skipped"] = "success"
    failure_reason_category: str | None = Field(None, max_length=80)
    failure_reason: str | None = Field(None, max_length=4000)
    elapsed_ms: int = Field(0, ge=0)
    metadata_json: dict | None = None


class AgentEvaluationResultCreateRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=64)
    agent_type: str = Field(..., min_length=1, max_length=80)
    agent_name: str = Field(..., min_length=1, max_length=120)
    run_id: str | None = Field(None, max_length=64)
    status: Literal["completed", "failed", "partial", "cancelled"]
    expected_status: Literal["completed", "failed", "partial", "cancelled"] = "completed"
    completion_score: float = Field(0, ge=0, le=1)
    failure_reason_category: str | None = Field(None, max_length=80)
    failure_reason: str | None = Field(None, max_length=4000)
    elapsed_ms: int = Field(0, ge=0)
    metadata_json: dict | None = None
