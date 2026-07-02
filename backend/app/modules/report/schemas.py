from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class GenerateReportRequest(BaseModel):
    report_type: Literal["daily", "weekly", "monthly"] = Field("daily", description="报告类型")
    report_date: date | None = Field(None, description="报告归属日期，默认取今天")
