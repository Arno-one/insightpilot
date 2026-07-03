from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event


def _resolve_event_window(task: dict[str, Any], happened_at: datetime | None = None) -> tuple[datetime, datetime]:
    if task.get("due_at"):
        start_at = datetime.fromisoformat(str(task["due_at"])) - timedelta(minutes=30)
    else:
        start_at = (happened_at or datetime.now()) + timedelta(hours=4)
    end_at = start_at + timedelta(minutes=30)
    return start_at, end_at


def create_follow_up_calendar_event(
    db: Session,
    *,
    tenant_id: str,
    approval: dict[str, Any],
    task: dict[str, Any],
    creator_user_id: str,
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：先生成平台内日程占位，后续再把这层 adapter 接到真实日历系统。"""

    existing = db.execute(
        text(
            """
            SELECT event_id, task_id, approval_id, customer_id, owner_user_id, title, description,
                   start_at, end_at, status, created_by_user_id, created_at
            FROM internal_calendar_event
            WHERE tenant_id = :tenant_id
              AND task_id = :task_id
              AND owner_user_id = :owner_user_id
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "task_id": task["task_id"],
            "owner_user_id": task["assignee_user_id"],
        },
    ).mappings().first()
    if existing:
        row = dict(existing)
        row["start_at"] = row["start_at"].isoformat() if row.get("start_at") else None
        row["end_at"] = row["end_at"].isoformat() if row.get("end_at") else None
        row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else None
        return row

    start_at, end_at = _resolve_event_window(task, happened_at)
    event_id = new_id("cal")
    title = f"跟进客户：{task['title']}"
    description = (
        f"客户 {approval['customer_id']} 的任务已进入执行，"
        f"建议按任务说明安排回访。"
    )
    db.execute(
        text(
            """
            INSERT INTO internal_calendar_event (
              tenant_id, event_id, task_id, approval_id, customer_id, owner_user_id,
              title, description, start_at, end_at, status, created_by_user_id
            )
            VALUES (
              :tenant_id, :event_id, :task_id, :approval_id, :customer_id, :owner_user_id,
              :title, :description, :start_at, :end_at, 'scheduled', :created_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "event_id": event_id,
            "task_id": task["task_id"],
            "approval_id": approval["approval_id"],
            "customer_id": approval["customer_id"],
            "owner_user_id": task["assignee_user_id"],
            "title": title,
            "description": description,
            "start_at": start_at,
            "end_at": end_at,
            "created_by_user_id": creator_user_id,
        },
    )
    log_workflow_event(
        db,
        tenant_id=tenant_id,
        entity_type="task",
        entity_id=task["task_id"],
        approval_id=approval["approval_id"],
        task_id=task["task_id"],
        customer_id=approval["customer_id"],
        risk_snapshot_id=approval.get("risk_snapshot_id"),
        action_type="calendar_event_created",
        operator_user_id=creator_user_id,
        note="已为任务创建平台内跟进日程",
        detail={
            "event_id": event_id,
            "owner_user_id": task["assignee_user_id"],
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
        happened_at=happened_at or datetime.now(),
    )
    return {
        "event_id": event_id,
        "task_id": task["task_id"],
        "approval_id": approval["approval_id"],
        "customer_id": approval["customer_id"],
        "owner_user_id": task["assignee_user_id"],
        "title": title,
        "description": description,
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "status": "scheduled",
        "created_by_user_id": creator_user_id,
        "created_at": (happened_at or datetime.now()).isoformat(),
    }
