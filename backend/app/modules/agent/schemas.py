from pydantic import BaseModel, Field


class RiskChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
