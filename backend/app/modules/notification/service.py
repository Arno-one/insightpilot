from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.notification import email_service
from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event


def _serialize_notification_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "delivered_at": row["delivered_at"].isoformat() if row.get("delivered_at") else None,
        "read_at": row["read_at"].isoformat() if row.get("read_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _build_task_assignment_message(approval: dict[str, Any], task: dict[str, Any]) -> tuple[str, str]:
    title = f"新任务：{task['title']}"
    content = (
        f"客户 {approval['customer_id']} 已生成新的 AI 跟进任务，"
        f"请在 {task.get('due_at') or '尽快'} 前处理。"
    )
    return title, content


def _load_recipient_user(db: Session, *, tenant_id: str, user_id: str) -> dict[str, Any] | None:
    return db.execute(
        text(
            """
            SELECT user_id, username, real_name, email, status, is_deleted
            FROM sys_user
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    ).mappings().first()


def _insert_notification_record(
    db: Session,
    *,
    tenant_id: str,
    notification_id: str,
    task: dict[str, Any],
    approval: dict[str, Any],
    sender_user_id: str,
    title: str,
    content: str,
    channel: str,
    delivered_at: datetime,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO internal_notification (
              tenant_id, notification_id, task_id, approval_id, customer_id, recipient_user_id,
              sender_user_id, notification_type, channel, title, content, status, delivered_at
            )
            VALUES (
              :tenant_id, :notification_id, :task_id, :approval_id, :customer_id, :recipient_user_id,
              :sender_user_id, 'task_assignment', :channel, :title, :content, 'sent', :delivered_at
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
            "channel": channel,
            "title": title,
            "content": content,
            "delivered_at": delivered_at,
        },
    )


def create_task_assignment_notification(
    db: Session,
    *,
    tenant_id: str,
    approval: dict[str, Any],
    task: dict[str, Any],
    sender_user_id: str,
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：优先走真实邮件通道，发信失败时自动回退到平台内通知，避免审批闭环中断。"""

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
        return _serialize_notification_row(dict(existing))

    delivered_at = happened_at or datetime.now()
    notification_id = new_id("notify")
    title, content = _build_task_assignment_message(approval, task)
    recipient = _load_recipient_user(db, tenant_id=tenant_id, user_id=task["assignee_user_id"])
    recipient_email = None
    channel = "internal"
    note = "任务通知已回退到平台内通知中心"
    fallback_reason: str | None = None

    if not recipient or recipient["status"] != 1 or recipient["is_deleted"] != 0:
        fallback_reason = "任务负责人不存在或已失效"
    else:
        recipient_email = (recipient.get("email") or "").strip() or None
        if not recipient_email:
            fallback_reason = "任务负责人未配置邮箱"
        else:
            try:
                email_service.send_task_assignment_email(
                    recipient_email=recipient_email,
                    recipient_name=recipient.get("real_name") or recipient.get("username"),
                    task=task,
                    approval=approval,
                )
                channel = "email"
                note = "任务通知邮件已发送"
            except Exception as exc:  # pragma: no cover - 失败分支由测试用 monkeypatch 显式覆盖
                fallback_reason = f"邮件发送失败：{exc}"

    _insert_notification_record(
        db,
        tenant_id=tenant_id,
        notification_id=notification_id,
        task=task,
        approval=approval,
        sender_user_id=sender_user_id,
        title=title,
        content=content,
        channel=channel,
        delivered_at=delivered_at,
    )
    detail = {
        "notification_id": notification_id,
        "recipient_user_id": task["assignee_user_id"],
        "channel": channel,
        "title": title,
    }
    if recipient_email:
        detail["recipient_email"] = recipient_email
    if fallback_reason:
        detail["fallback_reason"] = fallback_reason

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
        note=note,
        detail=detail,
        happened_at=delivered_at,
    )
    result = {
        "notification_id": notification_id,
        "task_id": task["task_id"],
        "approval_id": approval["approval_id"],
        "customer_id": approval["customer_id"],
        "recipient_user_id": task["assignee_user_id"],
        "sender_user_id": sender_user_id,
        "notification_type": "task_assignment",
        "channel": channel,
        "title": title,
        "content": content,
        "status": "sent",
        "delivered_at": delivered_at.isoformat(),
        "read_at": None,
        "created_at": delivered_at.isoformat(),
    }
    if recipient_email:
        result["recipient_email"] = recipient_email
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result
