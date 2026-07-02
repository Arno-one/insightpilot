from typing import Literal

from pydantic import BaseModel, Field


class RejectApprovalRequest(BaseModel):
    review_comment: str | None = Field(None, max_length=500, description="审批驳回备注")


class BatchReviewRequest(BaseModel):
    approval_ids: list[str] = Field(..., min_length=1, max_length=100, description="需要批量处理的审批 ID 列表")
    action: Literal["approve", "reject"] = Field(..., description="批量审批动作")
    review_comment: str | None = Field(None, max_length=500, description="批量审批备注")


class ApproveWithChangesRequest(BaseModel):
    title: str | None = Field(None, max_length=150)
    description: str | None = None
    assignee_user_id: str | None = Field(None, max_length=64)
    priority: str | None = Field(None, max_length=20)
    recommended_script: str | None = None
    review_comment: str | None = Field(None, max_length=500)
