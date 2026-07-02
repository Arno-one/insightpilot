from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.task.schemas import UpdateTaskStatusRequest
from app.shared.ids import new_id
from app.shared.response import success

router = APIRouter()


def _task_scope_where(current_user: dict) -> str:
    """按当前用户的任务可见范围拼接 SQL 条件，保持列表和更新权限一致。"""
    if "task:read:all" in current_user["permission_codes"] or "task:read:team" in current_user["permission_codes"]:
        return "t.tenant_id = :tenant_id"
    return "t.tenant_id = :tenant_id AND t.assignee_user_id = :user_id"


def _load_task_for_update(db: Session, current_user: dict, task_id: str) -> dict:
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "task_id": task_id,
    }
    where_sql = _task_scope_where(current_user)
    row = db.execute(
        text(
            f"""
            SELECT t.*, a.risk_snapshot_id
            FROM sales_task t
            LEFT JOIN approval_record a
              ON a.tenant_id = t.tenant_id
             AND a.approval_id = t.approval_id
            WHERE {where_sql}
              AND t.task_id = :task_id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在或无权操作")
    return dict(row)


def _validate_transition(current_status: str, target_status: str):
    allowed_transitions = {
        "pending": {"in_progress", "completed", "cancelled"},
        "in_progress": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }
    if current_status == target_status:
        return
    if target_status not in allowed_transitions.get(current_status, set()):
        raise HTTPException(status_code=400, detail=f"任务状态不能从 {current_status} 变更为 {target_status}")


def _create_follow_up_from_task(
    db: Session,
    current_user: dict,
    task: dict,
    data: UpdateTaskStatusRequest,
) -> str:
    """任务完成时自动回写一条跟进记录，保证执行结果能回流到 CRM。"""
    follow_up_id = new_id("fu")
    occurred_at = datetime.now()
    result_note = data.result_note or "已按任务要求完成本次跟进。"
    follow_up_content = data.follow_up_content or f"完成任务《{task['title']}》：{result_note}"

    db.execute(
        text(
            """
            INSERT INTO crm_follow_up_record (
              tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type,
              content, sentiment, customer_feedback, next_action, next_follow_up_at, occurred_at
            )
            VALUES (
              :tenant_id, :follow_up_id, :customer_id, :deal_id, :owner_user_id, :follow_up_type,
              :content, :sentiment, :customer_feedback, :next_action, :next_follow_up_at, :occurred_at
            )
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "follow_up_id": follow_up_id,
            "customer_id": task["customer_id"],
            "deal_id": task.get("deal_id"),
            "owner_user_id": current_user["user_id"],
            "follow_up_type": data.follow_up_type or "phone",
            "content": follow_up_content,
            "sentiment": data.sentiment or "neutral",
            "customer_feedback": data.customer_feedback,
            "next_action": data.next_action or result_note[:255],
            "next_follow_up_at": data.next_follow_up_at,
            "occurred_at": occurred_at,
        },
    )

    db.execute(
        text(
            """
            UPDATE crm_customer
            SET last_follow_up_at = :last_follow_up_at,
                next_follow_up_at = :next_follow_up_at,
                last_sentiment = :last_sentiment
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "customer_id": task["customer_id"],
            "last_follow_up_at": occurred_at,
            "next_follow_up_at": data.next_follow_up_at,
            "last_sentiment": data.sentiment or "neutral",
        },
    )
    return follow_up_id


@router.get("")
def list_tasks(
    customer_id: str | None = None,
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "customer_id": customer_id,
    }
    where_sql = _task_scope_where(current_user)
    customer_filter = ""
    if customer_id:
        customer_filter = "AND t.customer_id = :customer_id"

    rows = db.execute(
        text(
            f"""
            SELECT t.task_id, t.approval_id, t.customer_id, c.customer_name, t.deal_id, t.assignee_user_id,
                   assignee.real_name AS assignee_user_name,
                   t.task_type, t.title, t.description, t.recommended_script, t.priority, t.status,
                   t.due_at, t.completed_at, t.result_note, t.created_at
            FROM sales_task t
            LEFT JOIN crm_customer c
              ON c.tenant_id = t.tenant_id
             AND c.customer_id = t.customer_id
            LEFT JOIN sys_user assignee
              ON assignee.tenant_id = t.tenant_id
             AND assignee.user_id = t.assignee_user_id
            WHERE {where_sql}
              {customer_filter}
            ORDER BY t.due_at ASC, t.created_at DESC
            LIMIT 100
            """
        ),
        params,
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.patch("/{task_id}/status")
def update_task_status(
    task_id: str,
    data: UpdateTaskStatusRequest,
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    task = _load_task_for_update(db, current_user, task_id)
    _validate_transition(task["status"], data.status)

    if task["status"] == data.status:
        return success(
            {"task_id": task_id, "status": task["status"], "follow_up_id": None},
            "任务状态未变化",
        )

    now = datetime.now()
    follow_up_id = None
    completed_at = None
    result_note = data.result_note or task.get("result_note")

    if data.status == "completed":
        follow_up_id = _create_follow_up_from_task(db, current_user, task, data)
        completed_at = now

    db.execute(
        text(
            """
            UPDATE sales_task
            SET status = :status,
                completed_at = :completed_at,
                result_note = :result_note
            WHERE tenant_id = :tenant_id AND task_id = :task_id
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "task_id": task_id,
            "status": data.status,
            "completed_at": completed_at,
            "result_note": result_note,
        },
    )

    if task.get("risk_snapshot_id"):
        risk_status = None
        if data.status == "completed":
            risk_status = "completed"
        elif data.status == "cancelled":
            risk_status = "ignored"

        if risk_status:
            db.execute(
                text(
                    """
                    UPDATE customer_risk_snapshot
                    SET status = :status
                    WHERE tenant_id = :tenant_id AND risk_snapshot_id = :risk_snapshot_id
                    """
                ),
                {
                    "tenant_id": current_user["tenant_id"],
                    "risk_snapshot_id": task["risk_snapshot_id"],
                    "status": risk_status,
                },
            )

    db.commit()
    return success(
        {
            "task_id": task_id,
            "status": data.status,
            "follow_up_id": follow_up_id,
            "completed_at": completed_at.isoformat() if completed_at else None,
        },
        "任务状态已更新",
    )
