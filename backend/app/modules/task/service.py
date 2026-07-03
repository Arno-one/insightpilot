from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event


def resolve_task_due_at(policy: str | None) -> datetime:
    """中文注释：审批 payload 里仍然沿用简化的截止时间策略，避免前端先被复杂日期配置卡住。"""

    now = datetime.now()
    if policy == "today":
        return now + timedelta(hours=8)
    if policy == "tomorrow":
        return now + timedelta(days=1)
    if policy == "in_2_days":
        return now + timedelta(days=2)
    return now + timedelta(days=2)


def _serialize_task_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "due_at": row["due_at"].isoformat() if row.get("due_at") else None,
        "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def create_task_from_approval(
    db: Session,
    *,
    approval: dict[str, Any],
    payload: dict[str, Any],
    reviewer_user_id: str,
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：把审批草稿转成正式销售任务，同时保证同一审批不会重复落任务。"""

    existing = db.execute(
        text(
            """
            SELECT task_id, approval_id, customer_id, deal_id, assignee_user_id, creator_user_id,
                   task_type, title, description, recommended_script, priority, status,
                   due_at, completed_at, result_note, created_at, updated_at
            FROM sales_task
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            LIMIT 1
            """
        ),
        {"tenant_id": approval["tenant_id"], "approval_id": approval["approval_id"]},
    ).mappings().first()
    if existing:
        return _serialize_task_row(dict(existing))

    task_id = new_id("task")
    due_at = resolve_task_due_at(payload.get("due_at"))
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
            "due_at": due_at,
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
    return {
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
        "status": "pending",
        "due_at": due_at.isoformat(),
        "completed_at": None,
        "result_note": None,
        "created_at": (happened_at or datetime.now()).isoformat(),
        "updated_at": (happened_at or datetime.now()).isoformat(),
    }
