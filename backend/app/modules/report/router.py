from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.modules.report import service as report_service
from app.modules.report.schemas import GenerateReportRequest
from app.shared.response import success

router = APIRouter()


def _enqueue_report_generation(current_user: dict, report_type: str, report_date: date | None):
    """兼容既有测试和调用点，内部实现已下沉到服务层。"""
    queue = get_default_queue()
    return queue.enqueue(
        "app.workers.report_jobs.generate_business_report",
        current_user["tenant_id"],
        current_user["user_id"],
        report_type,
        report_date.isoformat() if report_date else None,
        job_timeout=600,
    )


def _append_owner_filter(filters: list[str], params: dict, owner_user_id: str | None):
    """兼容既有测试和调用点，内部实现已下沉到服务层。"""
    return report_service.append_owner_filter(filters, params, owner_user_id)


@router.post("/generate")
def generate_report(
    data: GenerateReportRequest,
    current_user: dict = Depends(require_permission("agent:run:business_report")),
):
    job = _enqueue_report_generation(current_user, data.report_type, data.report_date)
    return success(
        {
            "job_id": job.id,
            "report_type": data.report_type,
            "report_date": data.report_date.isoformat() if data.report_date else None,
        },
        f"{data.report_type} 报告任务已提交",
    )


@router.post("/daily/generate")
def generate_daily_report(current_user: dict = Depends(require_permission("agent:run:business_report"))):
    job = _enqueue_report_generation(current_user, "daily", None)
    return success({"job_id": job.id, "report_type": "daily"}, "经营日报任务已提交")


@router.get("")
def list_reports(
    customer_id: str | None = None,
    owner_user_id: str | None = None,
    report_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    current_user: dict = Depends(require_permission("report:read:team")),
    db: Session = Depends(get_db),
):
    reports = report_service.query_reports(
        db,
        current_user,
        customer_id=customer_id,
        owner_user_id=owner_user_id,
        report_type=report_type,
        date_from=date_from,
        date_to=date_to,
    )
    return success(reports, "查询成功", total=len(reports))
