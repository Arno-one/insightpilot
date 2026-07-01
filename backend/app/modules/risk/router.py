from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.shared.response import success

router = APIRouter()


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


@router.get("/snapshots")
def list_risk_snapshots(
    current_user: dict = Depends(require_permission("crm:risk:read:team")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT risk_snapshot_id, customer_id, owner_user_id, risk_score, risk_level,
                   llm_reason, llm_suggestion, status, created_at
            FROM customer_risk_snapshot
            WHERE tenant_id = :tenant_id
            ORDER BY risk_score DESC, created_at DESC
            LIMIT 100
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))
