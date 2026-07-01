import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.approval.schemas import ApproveWithChangesRequest, RejectApprovalRequest
from app.shared.ids import new_id
from app.shared.response import success

router = APIRouter()


@router.get("")
def list_approvals(
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT ar.approval_id, ar.approval_type, ar.risk_snapshot_id, ar.customer_id,
                   ar.proposed_payload_json, ar.status, ar.requested_by_user_id, ar.reviewer_user_id, ar.created_at,
                   requester.real_name AS requested_by_user_name,
                   reviewer.real_name AS reviewer_user_name
            FROM approval_record ar
            LEFT JOIN sys_user requester
              ON requester.tenant_id = ar.tenant_id
             AND requester.user_id = ar.requested_by_user_id
            LEFT JOIN sys_user reviewer
              ON reviewer.tenant_id = ar.tenant_id
             AND reviewer.user_id = ar.reviewer_user_id
            WHERE ar.tenant_id = :tenant_id
            ORDER BY ar.created_at DESC
            LIMIT 100
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


def _loads_json(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    return json.loads(value)


def _resolve_due_at(policy: str | None):
    now = datetime.now()
    if policy == "today":
        return now + timedelta(hours=8)
    if policy == "tomorrow":
        return now + timedelta(days=1)
    if policy == "in_2_days":
        return now + timedelta(days=2)
    return now + timedelta(days=2)


def _create_task_from_approval(db: Session, approval: dict, payload: dict, reviewer_user_id: str) -> str:
    """审批通过后创建正式销售任务；AI 草稿本身不直接落任务。"""
    existing = db.execute(
        text(
            """
            SELECT task_id
            FROM sales_task
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            LIMIT 1
            """
        ),
        {"tenant_id": approval["tenant_id"], "approval_id": approval["approval_id"]},
    ).scalar_one_or_none()
    if existing:
        return existing

    task_id = new_id("task")
    db.execute(
        text(
            """
            INSERT INTO sales_task (
              tenant_id, task_id, approval_id, customer_id, deal_id, assignee_user_id,
              creator_user_id, task_type, title, description, recommended_script,
              priority, status, due_at
            )
            VALUES (
              :tenant_id, :task_id, :approval_id, :customer_id, :deal_id, :assignee_user_id,
              :creator_user_id, :task_type, :title, :description, :recommended_script,
              :priority, 'pending', :due_at
            )
            """
        ),
        {
            "tenant_id": approval["tenant_id"],
            "task_id": task_id,
            "approval_id": approval["approval_id"],
            "customer_id": approval["customer_id"],
            "deal_id": payload.get("deal_id"),
            "assignee_user_id": payload.get("assignee_user_id"),
            "creator_user_id": reviewer_user_id,
            "task_type": payload.get("task_type", "quote_follow"),
            "title": payload.get("title", "AI 风险跟进任务"),
            "description": payload.get("description"),
            "recommended_script": payload.get("recommended_script"),
            "priority": payload.get("priority", "medium"),
            "due_at": _resolve_due_at(payload.get("due_at")),
        },
    )
    return task_id


def _get_pending_approval(db: Session, tenant_id: str, approval_id: str) -> dict:
    approval = db.execute(
        text(
            """
            SELECT *
            FROM approval_record
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "approval_id": approval_id},
    ).mappings().first()
    if not approval:
        raise HTTPException(status_code=404, detail="审批记录不存在")
    if approval["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"审批记录状态不是 pending: {approval['status']}")
    return dict(approval)


@router.post("/{approval_id}/approve")
def approve(
    approval_id: str,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    approval = _get_pending_approval(db, current_user["tenant_id"], approval_id)
    payload = _loads_json(approval["proposed_payload_json"])
    task_id = _create_task_from_approval(db, approval, payload, current_user["user_id"])

    db.execute(
        text(
            """
            UPDATE approval_record
            SET status = 'approved',
                reviewer_user_id = :reviewer_user_id,
                reviewed_at = :reviewed_at,
                review_comment = :review_comment
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "approval_id": approval_id,
            "reviewer_user_id": current_user["user_id"],
            "reviewed_at": datetime.now(),
            "review_comment": "审批通过，已创建正式销售任务",
        },
    )
    if approval.get("risk_snapshot_id"):
        db.execute(
            text(
                """
                UPDATE customer_risk_snapshot
                SET status = 'converted'
                WHERE tenant_id = :tenant_id AND risk_snapshot_id = :risk_snapshot_id
                """
            ),
            {"tenant_id": current_user["tenant_id"], "risk_snapshot_id": approval["risk_snapshot_id"]},
        )
    db.commit()
    return success({"task_id": task_id}, "审批通过，已创建销售任务")


@router.post("/{approval_id}/reject")
def reject(
    approval_id: str,
    data: RejectApprovalRequest,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    approval = _get_pending_approval(db, current_user["tenant_id"], approval_id)
    db.execute(
        text(
            """
            UPDATE approval_record
            SET status = 'rejected',
                reviewer_user_id = :reviewer_user_id,
                reviewed_at = :reviewed_at,
                review_comment = :review_comment
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "approval_id": approval_id,
            "reviewer_user_id": current_user["user_id"],
            "reviewed_at": datetime.now(),
            "review_comment": data.review_comment or "审批驳回",
        },
    )
    if approval.get("risk_snapshot_id"):
        db.execute(
            text(
                """
                UPDATE customer_risk_snapshot
                SET status = 'ignored'
                WHERE tenant_id = :tenant_id AND risk_snapshot_id = :risk_snapshot_id
                """
            ),
            {"tenant_id": current_user["tenant_id"], "risk_snapshot_id": approval["risk_snapshot_id"]},
        )
    db.commit()
    return success(None, "审批已驳回")


@router.post("/{approval_id}/approve-with-changes")
def approve_with_changes(
    approval_id: str,
    data: ApproveWithChangesRequest,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    approval = _get_pending_approval(db, current_user["tenant_id"], approval_id)
    payload = _loads_json(approval["proposed_payload_json"])
    changes = data.model_dump(exclude_none=True)
    review_comment = changes.pop("review_comment", None)
    payload.update(changes)
    task_id = _create_task_from_approval(db, approval, payload, current_user["user_id"])

    db.execute(
        text(
            """
            UPDATE approval_record
            SET status = 'approved',
                proposed_payload_json = :proposed_payload_json,
                reviewer_user_id = :reviewer_user_id,
                reviewed_at = :reviewed_at,
                review_comment = :review_comment
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "approval_id": approval_id,
            "proposed_payload_json": json.dumps(payload, ensure_ascii=False),
            "reviewer_user_id": current_user["user_id"],
            "reviewed_at": datetime.now(),
            "review_comment": review_comment or "修改后审批通过",
        },
    )
    if approval.get("risk_snapshot_id"):
        db.execute(
            text(
                """
                UPDATE customer_risk_snapshot
                SET status = 'converted'
                WHERE tenant_id = :tenant_id AND risk_snapshot_id = :risk_snapshot_id
                """
            ),
            {"tenant_id": current_user["tenant_id"], "risk_snapshot_id": approval["risk_snapshot_id"]},
        )
    db.commit()
    return success({"task_id": task_id}, "修改后审批通过，已创建销售任务")
