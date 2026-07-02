import json
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from app.core.database import get_db
from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.modules.report.schemas import GenerateReportRequest
from app.shared.response import success

router = APIRouter()


def _loads_json(value):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {} if value != "[]" else []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _enqueue_report_generation(current_user: dict, report_type: str, report_date: date | None):
    queue = get_default_queue()
    job = queue.enqueue(
        "app.workers.report_jobs.generate_business_report",
        current_user["tenant_id"],
        current_user["user_id"],
        report_type,
        report_date.isoformat() if report_date else None,
        job_timeout=600,
    )
    return job


def _append_owner_filter(filters: list[str], params: dict, owner_user_id: str | None):
    if not owner_user_id:
        return
    # 中文注释：报告当前没有单独的负责人引用表，V1 先复用 metrics_json / risk_top_json 中的负责人痕迹完成负责人级下钻。
    filters.append(
        "AND (CAST(br.metrics_json AS CHAR) LIKE :owner_pattern OR CAST(br.risk_top_json AS CHAR) LIKE :owner_pattern)"
    )
    params["owner_pattern"] = f"%{owner_user_id}%"


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
    params = {
        "tenant_id": current_user["tenant_id"],
        "customer_id": customer_id,
        "owner_user_id": owner_user_id,
        "report_type": report_type,
        "date_from": date_from,
        "date_to": date_to,
    }
    filters: list[str] = []
    if customer_id:
        # 中文注释：当前报告中的客户引用仍沉在 risk_top_json，V1 先用包含匹配完成客户级钻取。
        filters.append("AND CAST(br.risk_top_json AS CHAR) LIKE :customer_pattern")
        params["customer_pattern"] = f"%{customer_id}%"
    _append_owner_filter(filters, params, owner_user_id)
    if report_type:
        filters.append("AND br.report_type = :report_type")
    if date_from:
        filters.append("AND br.report_date >= :date_from")
    if date_to:
        filters.append("AND br.report_date <= :date_to")

    rows = db.execute(
        text(
            f"""
            SELECT br.report_id, br.report_type, br.report_date, br.summary, br.suggestions, br.created_at,
                   br.created_by_user_id, creator.real_name AS created_by_user_name,
                   br.metrics_json, br.risk_top_json
            FROM business_report br
            LEFT JOIN sys_user creator
              ON creator.tenant_id = br.tenant_id
             AND creator.user_id = br.created_by_user_id
            WHERE br.tenant_id = :tenant_id
              {' '.join(filters)}
            ORDER BY br.report_date DESC, br.created_at DESC
            LIMIT 50
            """
        ),
        params,
    ).mappings().all()

    reports = []
    for row in rows:
        item = dict(row)
        item["metrics_json"] = _loads_json(item.get("metrics_json"))
        item["risk_top_json"] = _loads_json(item.get("risk_top_json"))
        reports.append(item)
    return success(reports, "查询成功", total=len(reports))
