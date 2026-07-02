import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from app.core.database import get_db
from app.modules.approval.schemas import (
    ApproveWithChangesRequest,
    BatchReviewRequest,
    RejectApprovalRequest,
)
from app.modules.approval.service import sync_agent_run_after_approval_review
from app.modules.auth.dependencies import require_permission
from app.shared.ids import new_id
from app.shared.response import success
from app.shared.workflow_event import log_workflow_event

router = APIRouter()


def _parse_filter_datetime(value: str | None, field_name: str, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            base = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                return base + timedelta(days=1) - timedelta(seconds=1)
            return base
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 时间格式不正确") from exc


def _loads_json(value):
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _resolve_due_at(policy: str | None):
    now = datetime.now()
    if policy == "today":
        return now + timedelta(hours=8)
    if policy == "tomorrow":
        return now + timedelta(days=1)
    if policy == "in_2_days":
        return now + timedelta(days=2)
    return now + timedelta(days=2)


def _update_risk_snapshot_status(db: Session, tenant_id: str, risk_snapshot_id: str | None, status: str):
    if not risk_snapshot_id:
        return
    db.execute(
        text(
            """
            UPDATE customer_risk_snapshot
            SET status = :status
            WHERE tenant_id = :tenant_id AND risk_snapshot_id = :risk_snapshot_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "risk_snapshot_id": risk_snapshot_id,
            "status": status,
        },
    )


def _create_task_from_approval(
    db: Session,
    approval: dict,
    payload: dict,
    reviewer_user_id: str,
    happened_at: datetime | None = None,
) -> str:
    """审批通过后创建正式销售任务，避免同一条审批重复落任务。"""
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
    log_workflow_event(
        db,
        tenant_id=approval["tenant_id"],
        entity_type="task",
        entity_id=task_id,
        approval_id=approval["approval_id"],
        task_id=task_id,
        customer_id=approval["customer_id"],
        risk_snapshot_id=approval.get("risk_snapshot_id"),
        action_type="task_created",
        operator_user_id=reviewer_user_id,
        note="审批通过后已创建正式销售任务",
        detail={
            "task_type": payload.get("task_type", "quote_follow"),
            "title": payload.get("title", "AI 风险跟进任务"),
            "priority": payload.get("priority", "medium"),
            "assignee_user_id": payload.get("assignee_user_id"),
        },
        happened_at=happened_at,
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


def _approve_approval(
    db: Session,
    current_user: dict,
    approval: dict,
    payload: dict,
    *,
    review_comment: str,
    action_type: str,
    changes: dict | None = None,
) -> dict:
    reviewed_at = datetime.now()
    update_fields = [
        "status = 'approved'",
        "reviewer_user_id = :reviewer_user_id",
        "reviewed_at = :reviewed_at",
        "review_comment = :review_comment",
    ]
    params = {
        "tenant_id": current_user["tenant_id"],
        "approval_id": approval["approval_id"],
        "reviewer_user_id": current_user["user_id"],
        "reviewed_at": reviewed_at,
        "review_comment": review_comment,
    }
    if changes is not None:
        update_fields.insert(1, "proposed_payload_json = :proposed_payload_json")
        params["proposed_payload_json"] = json.dumps(payload, ensure_ascii=False)

    db.execute(
        text(
            f"""
            UPDATE approval_record
            SET {', '.join(update_fields)}
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            """
        ),
        params,
    )
    log_workflow_event(
        db,
        tenant_id=current_user["tenant_id"],
        entity_type="approval",
        entity_id=approval["approval_id"],
        approval_id=approval["approval_id"],
        customer_id=approval["customer_id"],
        risk_snapshot_id=approval.get("risk_snapshot_id"),
        action_type=action_type,
        operator_user_id=current_user["user_id"],
        note=review_comment,
        detail={
            "review_comment": review_comment,
            "changes": changes,
        },
        happened_at=reviewed_at,
    )
    task_id = _create_task_from_approval(
        db,
        approval,
        payload,
        current_user["user_id"],
        happened_at=reviewed_at,
    )
    _update_risk_snapshot_status(
        db,
        current_user["tenant_id"],
        approval.get("risk_snapshot_id"),
        "converted",
    )
    sync_agent_run_after_approval_review(
        db,
        tenant_id=current_user["tenant_id"],
        approval=approval,
        reviewed_status="approved",
        reviewed_at=reviewed_at,
        review_comment=review_comment,
        reviewer_user_id=current_user["user_id"],
        reviewer_user_name=current_user.get("real_name") or current_user.get("username"),
        task_id=task_id,
    )
    return {
        "approval_id": approval["approval_id"],
        "status": "approved",
        "task_id": task_id,
        "reviewed_at": reviewed_at.isoformat(),
        "review_comment": review_comment,
    }


def _reject_approval(db: Session, current_user: dict, approval: dict, review_comment: str) -> dict:
    reviewed_at = datetime.now()
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
            "approval_id": approval["approval_id"],
            "reviewer_user_id": current_user["user_id"],
            "reviewed_at": reviewed_at,
            "review_comment": review_comment,
        },
    )
    log_workflow_event(
        db,
        tenant_id=current_user["tenant_id"],
        entity_type="approval",
        entity_id=approval["approval_id"],
        approval_id=approval["approval_id"],
        customer_id=approval["customer_id"],
        risk_snapshot_id=approval.get("risk_snapshot_id"),
        action_type="approval_rejected",
        operator_user_id=current_user["user_id"],
        note=review_comment,
        detail={"review_comment": review_comment},
        happened_at=reviewed_at,
    )
    _update_risk_snapshot_status(
        db,
        current_user["tenant_id"],
        approval.get("risk_snapshot_id"),
        "ignored",
    )
    sync_agent_run_after_approval_review(
        db,
        tenant_id=current_user["tenant_id"],
        approval=approval,
        reviewed_status="rejected",
        reviewed_at=reviewed_at,
        review_comment=review_comment,
        reviewer_user_id=current_user["user_id"],
        reviewer_user_name=current_user.get("real_name") or current_user.get("username"),
        task_id=None,
    )
    return {
        "approval_id": approval["approval_id"],
        "status": "rejected",
        "reviewed_at": reviewed_at.isoformat(),
        "review_comment": review_comment,
    }


def _build_batch_message(action_label: str, success_count: int, failed_count: int) -> str:
    return f"{action_label}完成，成功 {success_count} 条，失败 {failed_count} 条"


@router.get("")
def list_approvals(
    customer_id: str | None = None,
    related_user_id: str | None = None,
    status: str | None = None,
    reviewer_keyword: str | None = None,
    requester_keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    params = {
        "tenant_id": current_user["tenant_id"],
        "customer_id": customer_id,
        "related_user_id": related_user_id,
        "status": status,
        "reviewer_keyword": f"%{reviewer_keyword}%" if reviewer_keyword else None,
        "requester_keyword": f"%{requester_keyword}%" if requester_keyword else None,
        "date_from": _parse_filter_datetime(date_from, "date_from"),
        "date_to": _parse_filter_datetime(date_to, "date_to", end_of_day=True),
    }
    filters: list[str] = []
    if customer_id:
        filters.append("AND ar.customer_id = :customer_id")
    if related_user_id:
        # 中文注释：负责人下钻时，需要把“发起人、审批人、payload 里的任务负责人”三类相关审批一起找出来。
        filters.append(
            "AND (ar.requested_by_user_id = :related_user_id OR ar.reviewer_user_id = :related_user_id "
            "OR JSON_UNQUOTE(JSON_EXTRACT(ar.proposed_payload_json, '$.assignee_user_id')) = :related_user_id)"
        )
    if status:
        filters.append("AND ar.status = :status")
    if reviewer_keyword:
        filters.append(
            "AND (ar.reviewer_user_id LIKE :reviewer_keyword OR reviewer.real_name LIKE :reviewer_keyword)"
        )
    if requester_keyword:
        filters.append(
            "AND (ar.requested_by_user_id LIKE :requester_keyword OR requester.real_name LIKE :requester_keyword)"
        )
    if params["date_from"]:
        filters.append("AND ar.created_at >= :date_from")
    if params["date_to"]:
        filters.append("AND ar.created_at <= :date_to")
    rows = db.execute(
        text(
            f"""
            SELECT ar.approval_id, ar.approval_type, ar.risk_snapshot_id, ar.customer_id,
                   c.customer_name,
                   ar.proposed_payload_json, ar.status, ar.requested_by_user_id, ar.reviewer_user_id, ar.created_at,
                   requester.real_name AS requested_by_user_name,
                   reviewer.real_name AS reviewer_user_name
            FROM approval_record ar
            LEFT JOIN crm_customer c
              ON c.tenant_id = ar.tenant_id
             AND c.customer_id = ar.customer_id
            LEFT JOIN sys_user requester
              ON requester.tenant_id = ar.tenant_id
             AND requester.user_id = ar.requested_by_user_id
            LEFT JOIN sys_user reviewer
              ON reviewer.tenant_id = ar.tenant_id
             AND reviewer.user_id = ar.reviewer_user_id
            WHERE ar.tenant_id = :tenant_id
              {' '.join(filters)}
            ORDER BY ar.created_at DESC
            LIMIT 100
            """
        ),
        params,
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.post("/batch-review")
def batch_review(
    data: BatchReviewRequest,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    approval_ids = list(dict.fromkeys(data.approval_ids))
    success_items: list[dict] = []
    failed_items: list[dict] = []

    for approval_id in approval_ids:
        try:
            # 中文注释：批量操作按单条事务切分，保证某一条失败时不会把前面已成功的审批一起回滚。
            with db.begin_nested():
                approval = _get_pending_approval(db, current_user["tenant_id"], approval_id)
                if data.action == "approve":
                    result = _approve_approval(
                        db,
                        current_user,
                        approval,
                        _loads_json(approval["proposed_payload_json"]),
                        review_comment=data.review_comment or "审批已通过，已创建正式销售任务",
                        action_type="approval_approved",
                    )
                else:
                    result = _reject_approval(
                        db,
                        current_user,
                        approval,
                        data.review_comment or "审批已驳回",
                    )
                success_items.append(result)
        except HTTPException as exc:
            failed_items.append(
                {
                    "approval_id": approval_id,
                    "message": exc.detail,
                }
            )

    db.commit()
    return success(
        {
            "items": success_items,
            "failed_items": failed_items,
            "success_count": len(success_items),
            "failed_count": len(failed_items),
        },
        _build_batch_message("批量审批", len(success_items), len(failed_items)),
        total=len(success_items),
    )


@router.post("/{approval_id}/approve")
def approve(
    approval_id: str,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    approval = _get_pending_approval(db, current_user["tenant_id"], approval_id)
    result = _approve_approval(
        db,
        current_user,
        approval,
        _loads_json(approval["proposed_payload_json"]),
        review_comment="审批已通过，已创建正式销售任务",
        action_type="approval_approved",
    )
    db.commit()
    return success({"task_id": result["task_id"]}, result["review_comment"])


@router.post("/{approval_id}/reject")
def reject(
    approval_id: str,
    data: RejectApprovalRequest,
    current_user: dict = Depends(require_permission("approval:review:agent_task")),
    db: Session = Depends(get_db),
):
    approval = _get_pending_approval(db, current_user["tenant_id"], approval_id)
    result = _reject_approval(
        db,
        current_user,
        approval,
        data.review_comment or "审批已驳回",
    )
    db.commit()
    return success(None, result["review_comment"])


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
    review_comment = changes.pop("review_comment", None) or "修改后审批通过"
    payload.update(changes)
    result = _approve_approval(
        db,
        current_user,
        approval,
        payload,
        review_comment=review_comment,
        action_type="approval_approved_with_changes",
        changes=changes,
    )
    db.commit()
    return success({"task_id": result["task_id"]}, "修改后审批通过，已创建销售任务")
