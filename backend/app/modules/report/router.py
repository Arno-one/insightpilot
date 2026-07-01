from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.shared.response import success

router = APIRouter()


@router.post("/daily/generate")
def generate_daily_report(current_user: dict = Depends(require_permission("agent:run:business_report"))):
    queue = get_default_queue()
    job = queue.enqueue(
        "app.workers.report_jobs.generate_daily_report",
        current_user["tenant_id"],
        current_user["user_id"],
        job_timeout=600,
    )
    return success({"job_id": job.id}, "经营日报任务已提交")


@router.get("")
def list_reports(
    current_user: dict = Depends(require_permission("report:read:team")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT br.report_id, br.report_type, br.report_date, br.summary, br.suggestions, br.created_at,
                   br.created_by_user_id, creator.real_name AS created_by_user_name
            FROM business_report br
            LEFT JOIN sys_user creator
              ON creator.tenant_id = br.tenant_id
             AND creator.user_id = br.created_by_user_id
            WHERE br.tenant_id = :tenant_id
            ORDER BY br.report_date DESC, br.created_at DESC
            LIMIT 50
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))
