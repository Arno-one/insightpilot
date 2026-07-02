from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.task.schemas import (
    BatchAssignTaskRequest,
    BatchUpdateTaskStatusRequest,
    UpdateTaskStatusRequest,
)
from app.shared.ids import new_id
from app.shared.response import success
from app.shared.workflow_event import log_workflow_event

router = APIRouter()


def _normalize_bool_filter(value: bool | None) -> bool:
    return bool(value)


def _task_scope_where(current_user: dict) -> str:
    """按当前用户的任务可见范围拼接 SQL 条件，保持列表与更新权限一致。"""
    if "task:read:all" in current_user["permission_codes"] or "task:read:team" in current_user["permission_codes"]:
        return "t.tenant_id = :tenant_id"
    return "t.tenant_id = :tenant_id AND t.assignee_user_id = :user_id"


def _can_manage_task_assignment(current_user: dict) -> bool:
    permission_codes = set(current_user["permission_codes"])
    return "task:read:all" in permission_codes or "task:read:team" in permission_codes


def _ensure_assignment_permission(current_user: dict):
    if not _can_manage_task_assignment(current_user):
        raise HTTPException(status_code=403, detail="当前账号仅可处理自己的任务，不能批量分配负责人")


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


def _load_assignable_user(db: Session, tenant_id: str, user_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT user_id, username, real_name, status, is_deleted
            FROM sys_user
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
    ).mappings().first()
    if not row or row["status"] != 1 or row["is_deleted"] != 0:
        raise HTTPException(status_code=404, detail="负责人不存在或不可分配")
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
    data: UpdateTaskStatusRequest | BatchUpdateTaskStatusRequest,
    happened_at: datetime,
) -> str:
    """任务完成时自动回写一条跟进记录，保证执行结果能回流到 CRM。"""
    follow_up_id = new_id("fu")
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
            "occurred_at": happened_at,
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
            "last_follow_up_at": happened_at,
            "next_follow_up_at": data.next_follow_up_at,
            "last_sentiment": data.sentiment or "neutral",
        },
    )
    return follow_up_id


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


def _apply_task_status_update(
    db: Session,
    current_user: dict,
    task: dict,
    data: UpdateTaskStatusRequest | BatchUpdateTaskStatusRequest,
) -> dict:
    _validate_transition(task["status"], data.status)

    if task["status"] == data.status:
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "follow_up_id": None,
            "completed_at": task["completed_at"].isoformat() if task.get("completed_at") else None,
            "unchanged": True,
        }

    now = datetime.now()
    follow_up_id = None
    completed_at = None
    result_note = data.result_note or task.get("result_note")

    if data.status == "completed":
        follow_up_id = _create_follow_up_from_task(db, current_user, task, data, happened_at=now)
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
            "task_id": task["task_id"],
            "status": data.status,
            "completed_at": completed_at,
            "result_note": result_note,
        },
    )

    if data.status == "completed":
        _update_risk_snapshot_status(db, current_user["tenant_id"], task.get("risk_snapshot_id"), "completed")
    elif data.status == "cancelled":
        _update_risk_snapshot_status(db, current_user["tenant_id"], task.get("risk_snapshot_id"), "ignored")

    action_type = {
        "in_progress": "task_in_progress",
        "completed": "task_completed",
        "cancelled": "task_cancelled",
    }[data.status]
    action_note = {
        "in_progress": "任务已开始执行",
        "completed": "任务已完成，并已回写跟进记录",
        "cancelled": "任务已取消",
    }[data.status]
    log_workflow_event(
        db,
        tenant_id=current_user["tenant_id"],
        entity_type="task",
        entity_id=task["task_id"],
        approval_id=task.get("approval_id"),
        task_id=task["task_id"],
        customer_id=task["customer_id"],
        risk_snapshot_id=task.get("risk_snapshot_id"),
        action_type=action_type,
        operator_user_id=current_user["user_id"],
        note=result_note or action_note,
        detail={
            "status": data.status,
            "result_note": result_note,
            "follow_up_id": follow_up_id,
            "sentiment": data.sentiment,
            "customer_feedback": data.customer_feedback,
            "next_action": data.next_action,
            "next_follow_up_at": data.next_follow_up_at,
        },
        happened_at=now,
    )

    return {
        "task_id": task["task_id"],
        "status": data.status,
        "follow_up_id": follow_up_id,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "unchanged": False,
    }


def _reassign_task(db: Session, current_user: dict, task: dict, assignee: dict) -> dict:
    changed = task["assignee_user_id"] != assignee["user_id"]
    if changed:
        db.execute(
            text(
                """
                UPDATE sales_task
                SET assignee_user_id = :assignee_user_id
                WHERE tenant_id = :tenant_id AND task_id = :task_id
                """
            ),
            {
                "tenant_id": current_user["tenant_id"],
                "task_id": task["task_id"],
                "assignee_user_id": assignee["user_id"],
            },
        )
        log_workflow_event(
            db,
            tenant_id=current_user["tenant_id"],
            entity_type="task",
            entity_id=task["task_id"],
            approval_id=task.get("approval_id"),
            task_id=task["task_id"],
            customer_id=task["customer_id"],
            risk_snapshot_id=task.get("risk_snapshot_id"),
            action_type="task_reassigned",
            operator_user_id=current_user["user_id"],
            note=f"任务负责人已改为 {assignee['real_name'] or assignee['username'] or assignee['user_id']}",
            detail={
                "previous_assignee_user_id": task["assignee_user_id"],
                "assignee_user_id": assignee["user_id"],
            },
        )

    return {
        "task_id": task["task_id"],
        "assignee_user_id": assignee["user_id"],
        "assignee_user_name": assignee["real_name"] or assignee["username"] or assignee["user_id"],
        "unchanged": not changed,
    }


def _build_batch_message(action_label: str, success_count: int, failed_count: int) -> str:
    return f"{action_label}完成，成功 {success_count} 条，失败 {failed_count} 条"


@router.get("")
def list_tasks(
    customer_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    assignee_keyword: str | None = None,
    overdue_only: bool | None = None,
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "customer_id": customer_id,
        "status": status,
        "priority": priority,
        "assignee_keyword": f"%{assignee_keyword}%" if assignee_keyword else None,
    }
    where_sql = _task_scope_where(current_user)
    filters: list[str] = []
    if customer_id:
        filters.append("AND t.customer_id = :customer_id")
    if status:
        filters.append("AND t.status = :status")
    if priority:
        filters.append("AND t.priority = :priority")
    if assignee_keyword:
        filters.append("AND (t.assignee_user_id LIKE :assignee_keyword OR assignee.real_name LIKE :assignee_keyword)")
    if _normalize_bool_filter(overdue_only):
        # 中文注释：逾期筛选只看仍需推进的任务，已完成或已取消的记录不再计入风险队列。
        filters.append("AND t.status IN ('pending', 'in_progress') AND t.due_at IS NOT NULL AND t.due_at < NOW()")

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
              {' '.join(filters)}
            ORDER BY t.due_at ASC, t.created_at DESC
            LIMIT 100
            """
        ),
        params,
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.get("/assignees")
def list_task_assignees(
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    _ensure_assignment_permission(current_user)
    rows = db.execute(
        text(
            """
            SELECT user_id, username, real_name
            FROM sys_user
            WHERE tenant_id = :tenant_id AND status = 1 AND is_deleted = 0
            ORDER BY real_name ASC, username ASC
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
        },
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.patch("/batch/status")
def batch_update_task_status(
    data: BatchUpdateTaskStatusRequest,
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    task_ids = list(dict.fromkeys(data.task_ids))
    success_items: list[dict] = []
    failed_items: list[dict] = []

    for task_id in task_ids:
        try:
            with db.begin_nested():
                task = _load_task_for_update(db, current_user, task_id)
                success_items.append(_apply_task_status_update(db, current_user, task, data))
        except HTTPException as exc:
            failed_items.append(
                {
                    "task_id": task_id,
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
        _build_batch_message("批量更新任务状态", len(success_items), len(failed_items)),
        total=len(success_items),
    )


@router.patch("/batch/assignee")
def batch_assign_task(
    data: BatchAssignTaskRequest,
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    _ensure_assignment_permission(current_user)
    assignee = _load_assignable_user(db, current_user["tenant_id"], data.assignee_user_id)
    task_ids = list(dict.fromkeys(data.task_ids))
    success_items: list[dict] = []
    failed_items: list[dict] = []

    for task_id in task_ids:
        try:
            with db.begin_nested():
                task = _load_task_for_update(db, current_user, task_id)
                success_items.append(_reassign_task(db, current_user, task, assignee))
        except HTTPException as exc:
            failed_items.append(
                {
                    "task_id": task_id,
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
        _build_batch_message("批量分配负责人", len(success_items), len(failed_items)),
        total=len(success_items),
    )


@router.patch("/{task_id}/status")
def update_task_status(
    task_id: str,
    data: UpdateTaskStatusRequest,
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    task = _load_task_for_update(db, current_user, task_id)
    result = _apply_task_status_update(db, current_user, task, data)
    db.commit()

    if result["unchanged"]:
        return success(
            {"task_id": task_id, "status": result["status"], "follow_up_id": None},
            "任务状态未变化",
        )

    return success(
        {
            "task_id": task_id,
            "status": result["status"],
            "follow_up_id": result["follow_up_id"],
            "completed_at": result["completed_at"],
        },
        "任务状态已更新",
    )
