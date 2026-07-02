import json
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from app.core.queue import get_default_queue


def loads_json(value):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {} if value != "[]" else []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def enqueue_report_generation(current_user: dict, report_type: str, report_date: date | None):
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


def append_owner_filter(filters: list[str], params: dict, owner_user_id: str | None):
    if not owner_user_id:
        return
    # 中文注释：报告当前没有单独的负责人引用表，V1 先复用 metrics_json / risk_top_json 中的负责人痕迹完成负责人级下钻。
    filters.append(
        "AND (CAST(br.metrics_json AS CHAR) LIKE :owner_pattern OR CAST(br.risk_top_json AS CHAR) LIKE :owner_pattern)"
    )
    params["owner_pattern"] = f"%{owner_user_id}%"


def query_reports(
    db: Session,
    current_user: dict,
    *,
    customer_id: str | None = None,
    owner_user_id: str | None = None,
    report_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> list[dict]:
    params = {
        "tenant_id": current_user["tenant_id"],
        "customer_id": customer_id,
        "owner_user_id": owner_user_id,
        "report_type": report_type,
        "date_from": date_from,
        "date_to": date_to,
        "limit": max(1, min(limit, 100)),
    }
    filters: list[str] = []
    if customer_id:
        # 中文注释：当前报告中的客户引用仍沉在 risk_top_json，V1 先用包含匹配完成客户级钻取。
        filters.append("AND CAST(br.risk_top_json AS CHAR) LIKE :customer_pattern")
        params["customer_pattern"] = f"%{customer_id}%"
    append_owner_filter(filters, params, owner_user_id)
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
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    reports = []
    for row in rows:
        item = dict(row)
        item["metrics_json"] = loads_json(item.get("metrics_json"))
        item["risk_top_json"] = loads_json(item.get("risk_top_json"))
        reports.append(item)
    return reports
