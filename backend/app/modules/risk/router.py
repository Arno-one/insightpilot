from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.shared.response import success

router = APIRouter()


def _customer_scope_where(current_user: dict, alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if "crm:customer:read:all" in current_user["permission_codes"]:
        return f"{prefix}tenant_id = :tenant_id"
    if "crm:customer:read:team" in current_user["permission_codes"]:
        return f"{prefix}tenant_id = :tenant_id"
    return f"{prefix}tenant_id = :tenant_id AND {prefix}owner_user_id = :user_id"


def _ensure_customer_access(db: Session, current_user: dict, customer_id: str):
    """重算单客户风险前，先复用客户数据权限做一次校验，避免越权触发后台任务。"""
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "customer_id": customer_id,
    }
    where_sql = _customer_scope_where(current_user, "c")
    customer = db.execute(
        text(
            f"""
            SELECT c.customer_id
            FROM crm_customer c
            WHERE {where_sql}
              AND c.customer_id = :customer_id
            LIMIT 1
            """
        ),
        params,
    ).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在或无权触发风险重算")


@router.post("/scan")
def trigger_risk_scan(current_user: dict = Depends(require_permission("agent:run:risk_analysis"))):
    """触发风险扫描任务；真实扫描逻辑由 RQ Worker 异步执行。"""
    queue = get_default_queue()
    job = queue.enqueue(
        "app.workers.risk_jobs.run_risk_scan",
        current_user["tenant_id"],
        current_user["user_id"],
        job_timeout=600,
    )
    return success({"job_id": job.id}, "风险扫描任务已提交")


@router.post("/customers/{customer_id}/scan")
def trigger_single_customer_risk_scan(
    customer_id: str,
    current_user: dict = Depends(require_permission("agent:run:risk_analysis")),
    db: Session = Depends(get_db),
):
    _ensure_customer_access(db, current_user, customer_id)
    queue = get_default_queue()
    job = queue.enqueue(
        "app.workers.risk_jobs.run_risk_scan",
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
        job_timeout=600,
    )
    return success({"job_id": job.id, "customer_id": customer_id}, "当前客户风险重算任务已提交")


@router.get("/snapshots")
def list_risk_snapshots(
    current_user: dict = Depends(require_permission("crm:risk:read:team")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT rs.risk_snapshot_id, rs.customer_id, c.customer_name, rs.owner_user_id,
                   owner.real_name AS owner_user_name, rs.risk_score, rs.risk_level,
                   rs.llm_reason, rs.llm_suggestion, rs.status, rs.created_at
            FROM customer_risk_snapshot rs
            LEFT JOIN crm_customer c
              ON c.tenant_id = rs.tenant_id
             AND c.customer_id = rs.customer_id
            LEFT JOIN sys_user owner
              ON owner.tenant_id = rs.tenant_id
             AND owner.user_id = rs.owner_user_id
            WHERE rs.tenant_id = :tenant_id
            ORDER BY rs.risk_score DESC, rs.created_at DESC
            LIMIT 100
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))
