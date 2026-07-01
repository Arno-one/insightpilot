from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UpdateTaskStatusRequest(BaseModel):
    status: Literal["in_progress", "completed", "cancelled"] = Field(..., description="目标任务状态")
    result_note: str | None = Field(None, max_length=2000, description="任务执行结果备注")
    follow_up_type: str | None = Field("phone", max_length=30, description="完成任务后生成的跟进方式")
    follow_up_content: str | None = Field(None, max_length=4000, description="完成任务后写入的跟进内容")
    sentiment: Literal["positive", "neutral", "negative"] | None = Field("neutral", description="本次跟进情绪")
    customer_feedback: str | None = Field(None, max_length=255, description="客户反馈摘要")
    next_action: str | None = Field(None, max_length=255, description="下一步动作")
    next_follow_up_at: datetime | None = Field(None, description="下一次建议跟进时间")
