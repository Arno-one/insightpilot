from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=20)
    enable_rerank: bool = True


class RagHit(BaseModel):
    citation_id: str | None = None
    source_type: str
    doc_id: str
    section_id: str | None = None
    title: str | None = None
    text: str
    score: float | None = None
    rank_no: int


class RagCitation(BaseModel):
    citation_id: str
    source_type: str
    doc_id: str
    section_id: str | None = None
    title: str | None = None
    rank_no: int
    score: float | None = None
    ref: str
    text_preview: str


class RagSearchResponse(BaseModel):
    trace_id: str
    question: str
    rewritten_query: str
    hits: list[RagHit]
    citations: list[RagCitation] = Field(default_factory=list)
    answer_context: str


class RagEvaluateRequest(BaseModel):
    top_k: int = Field(5, ge=1, le=20)
    limit: int = Field(20, ge=1, le=100)
    enable_rerank: bool = True
