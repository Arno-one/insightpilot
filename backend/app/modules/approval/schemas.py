from pydantic import BaseModel, Field


class RejectApprovalRequest(BaseModel):
    review_comment: str | None = Field(None, max_length=500)


class ApproveWithChangesRequest(BaseModel):
    title: str | None = Field(None, max_length=150)
    description: str | None = None
    assignee_user_id: str | None = Field(None, max_length=64)
    priority: str | None = Field(None, max_length=20)
    recommended_script: str | None = None
    review_comment: str | None = Field(None, max_length=500)
