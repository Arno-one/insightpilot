from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event


def create_task_assignment_notification(
    db: Session,
    *,
    tenant_id: str,
    approval: dict[str, Any],
    task: dict[str, Any],
    sender_user_id: str,
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：先做平台内通知闭环，后面再把这个 adapter 接到企业微信、邮件等真实通道。"""

    existing = db.execute(
        text(
            """
            SELECT notification_id, task_id, approval_id, customer_id, recipient_user_id, sender_user_id,
                   notification_type, channel, title, content, status, delivered_at, read_at, created_at
            FROM internal_notification
            WHERE tenant_id = :tenant_id
              AND task_id = :task_id
              AND recipient_user_id = :recipient_user_id
              AND notification_type = 'task_assignment'
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "task_id": task["task_id"],
            "recipient_user_id": task["assignee_user_id"],
        },
    ).mappings().first()
    if existing:
        row = dict(existing)
        row["delivered_at"] = row["delivered_at"].isoformat() if row.get("delivered_at") else None
        row["read_at"] = row["read_at"].isoformat() if row.get("read_at") else None
        row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else None
        return row

    delivered_at = happened_at or datetime.now()
    notification_id = new_id("notify")
    title = f"新任务：{task['title']}"
    content = (
        f"客户 {approval['customer_id']} 已生成新的 AI 跟进任务，"
        f"请在 {task.get('due_at') or '尽快'} 前处理。"
    )
    db.execute(
        text(
            """
            INSERT INTO internal_notification (
              tenant_id, notification_id, task_id, approval_id, customer_id, recipient_user_id,
              sender_user_id, notification_type, channel, title, content, status, delivered_at
            )
            VALUES (
              :tenant_id, :notification_id, :task_id, :approval_id, :customer_id, :recipient_user_id,
              :sender_user_id, 'task_assignment', 'internal', :title, :content, 'sent', :delivered_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "notification_id": notification_id,
            "task_id": task["task_id"],
            "approval_id": approval["approval_id"],
            "customer_id": approval["customer_id"],
            "recipient_user_id": task["assignee_user_id"],
            "sender_user_id": sender_user_id,
            "title": title,
            "content": content,
            "delivered_at": delivered_at,
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
        action_type="notification_sent",
        operator_user_id=sender_user_id,
        note="任务通知已发送到平台内通知中心",
        detail={
            "notification_id": notification_id,
            "recipient_user_id": task["assignee_user_id"],
            "channel": "internal",
            "title": title,
        },
        happened_at=delivered_at,
    )
    return {
        "notification_id": notification_id,
        "task_id": task["task_id"],
        "approval_id": approval["approval_id"],
        "customer_id": approval["customer_id"],
        "recipient_user_id": task["assignee_user_id"],
        "sender_user_id": sender_user_id,
        "notification_type": "task_assignment",
        "channel": "internal",
        "title": title,
        "content": content,
        "status": "sent",
        "delivered_at": delivered_at.isoformat(),
        "read_at": None,
        "created_at": delivered_at.isoformat(),
    }
