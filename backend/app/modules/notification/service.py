from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.notification import email_service
from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event

MAIL_STATUS_SENT = "sent"
MAIL_STATUS_SENT_AFTER_RETRY = "sent_after_retry"
MAIL_STATUS_FAILED = "failed"
MAIL_STATUS_FALLBACK_INTERNAL = "fallback_internal"
MAIL_STATUS_SKIPPED = "skipped"

_FAILED_DELIVERY_STATUSES = (
    MAIL_STATUS_FAILED,
    MAIL_STATUS_FALLBACK_INTERNAL,
    MAIL_STATUS_SKIPPED,
)


def load_notification_operator_context(db: Session, *, tenant_id: str, user_id: str) -> dict[str, Any]:
    """中文注释：Mail MCP 和通知接口都要复用统一的用户上下文，避免每层重复拼权限查询。"""

    user = db.execute(
        text(
            """
            SELECT tenant_id, user_id, username, real_name, status, is_deleted
            FROM sys_user
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    ).mappings().first()
    if not user or user["status"] != 1 or user["is_deleted"] != 0:
        raise PermissionError("通知操作用户不存在或已失效")

    permission_codes = db.execute(
        text(
            """
            SELECT DISTINCT p.permission_code
            FROM sys_user_role ur
            JOIN sys_role_permission rp ON rp.tenant_id = ur.tenant_id AND rp.role_id = ur.role_id
            JOIN sys_permission p ON p.permission_id = rp.permission_id
            WHERE ur.tenant_id = :tenant_id
              AND ur.user_id = :user_id
              AND p.status = 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    ).scalars().all()

    return {
        "tenant_id": user["tenant_id"],
        "user_id": user["user_id"],
        "username": user["username"],
        "real_name": user["real_name"],
        "permission_codes": sorted(permission_codes),
    }


def _serialize_notification_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "delivered_at": row["delivered_at"].isoformat() if row.get("delivered_at") else None,
        "read_at": row["read_at"].isoformat() if row.get("read_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "last_attempted_at": row["last_attempted_at"].isoformat() if row.get("last_attempted_at") else None,
        "next_retry_at": row["next_retry_at"].isoformat() if row.get("next_retry_at") else None,
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


def _load_task_snapshot(db: Session, *, tenant_id: str, task_id: str) -> dict[str, Any]:
    task = db.execute(
        text(
            """
            SELECT task_id, title, description, priority, due_at, assignee_user_id
            FROM sales_task
            WHERE tenant_id = :tenant_id AND task_id = :task_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "task_id": task_id},
    ).mappings().first()
    if not task:
        raise LookupError("关联任务不存在，无法重试邮件通知")
    row = dict(task)
    if row.get("due_at"):
        row["due_at"] = row["due_at"].isoformat()
    return row


def _load_approval_snapshot(
    db: Session,
    *,
    tenant_id: str,
    approval_id: str | None,
    customer_id: str,
) -> dict[str, Any]:
    if not approval_id:
        return {"approval_id": None, "customer_id": customer_id}
    approval = db.execute(
        text(
            """
            SELECT approval_id, customer_id, risk_snapshot_id
            FROM approval_record
            WHERE tenant_id = :tenant_id AND approval_id = :approval_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "approval_id": approval_id},
    ).mappings().first()
    if approval:
        return dict(approval)
    return {"approval_id": approval_id, "customer_id": customer_id}


def _notification_scope_where(current_user: dict[str, Any], alias: str = "n") -> str:
    prefix = f"{alias}." if alias else ""
    permission_codes = current_user.get("permission_codes", [])
    if "task:read:all" in permission_codes or "task:read:team" in permission_codes:
        return f"{prefix}tenant_id = :tenant_id"
    if "task:read:self" in permission_codes or "approval:review:agent_task" in permission_codes:
        return (
            f"{prefix}tenant_id = :tenant_id AND "
            f"({prefix}recipient_user_id = :user_id OR {prefix}sender_user_id = :user_id)"
        )
    raise PermissionError("当前账号缺少通知查询权限")


def _load_notification_row(
    db: Session,
    *,
    tenant_id: str,
    notification_id: str,
    current_user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = {"tenant_id": tenant_id, "notification_id": notification_id}
    if current_user:
        params["user_id"] = current_user["user_id"]
        where_sql = _notification_scope_where(current_user)
    else:
        where_sql = "n.tenant_id = :tenant_id"
    row = db.execute(
        text(
            f"""
            SELECT n.notification_id, n.task_id, n.approval_id, n.customer_id, n.recipient_user_id,
                   n.sender_user_id, n.notification_type, n.channel, n.title, n.content, n.status,
                   n.delivered_at, n.read_at, n.created_at, n.delivery_status, n.provider,
                   n.provider_message_id, n.retry_count, n.last_attempted_at, n.next_retry_at,
                   n.last_error
            FROM internal_notification n
            WHERE {where_sql}
              AND n.notification_id = :notification_id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    if not row:
        raise LookupError("通知记录不存在或无权查看")
    return dict(row)


def _compute_next_retry_at(reference_time: datetime, retry_count: int) -> datetime:
    """中文注释：V1 先给出简单的指数退避建议时间，后续接调度器时可以直接复用。"""

    minutes = min(5 * (2 ** max(retry_count - 1, 0)), 60)
    return reference_time + timedelta(minutes=minutes)


def _normalize_mail_attempt_result(
    *,
    delivered_at: datetime,
    recipient: dict[str, Any] | None,
    recipient_email: str | None,
    send_result: dict[str, Any] | None,
    send_error: str | None,
    retry_count: int,
) -> dict[str, Any]:
    if send_result:
        return {
            "channel": "email",
            "status": "sent",
            "delivery_status": MAIL_STATUS_SENT if retry_count <= 1 else MAIL_STATUS_SENT_AFTER_RETRY,
            "provider": send_result.get("provider"),
            "provider_message_id": send_result.get("provider_message_id"),
            "retry_count": retry_count,
            "last_attempted_at": delivered_at,
            "next_retry_at": None,
            "last_error": None,
            "fallback_reason": None,
            "recipient_email": send_result.get("recipient_email") or recipient_email,
            "note": "任务通知邮件已发送" if retry_count <= 1 else "任务通知邮件已重试发送成功",
        }

    if not recipient or recipient["status"] != 1 or recipient["is_deleted"] != 0:
        return {
            "channel": "internal",
            "status": "sent",
            "delivery_status": MAIL_STATUS_SKIPPED,
            "provider": None,
            "provider_message_id": None,
            "retry_count": retry_count,
            "last_attempted_at": None,
            "next_retry_at": None,
            "last_error": "任务负责人不存在或已失效",
            "fallback_reason": "任务负责人不存在或已失效",
            "recipient_email": None,
            "note": "任务通知已回退到平台内通知中心",
        }

    if not recipient_email:
        return {
            "channel": "internal",
            "status": "sent",
            "delivery_status": MAIL_STATUS_SKIPPED,
            "provider": None,
            "provider_message_id": None,
            "retry_count": retry_count,
            "last_attempted_at": None,
            "next_retry_at": None,
            "last_error": "任务负责人未配置邮箱",
            "fallback_reason": "任务负责人未配置邮箱",
            "recipient_email": None,
            "note": "任务通知已回退到平台内通知中心",
        }

    if send_error and "SMTP 配置不完整" in send_error:
        return {
            "channel": "internal",
            "status": "sent",
            "delivery_status": MAIL_STATUS_SKIPPED,
            "provider": "smtp",
            "provider_message_id": None,
            "retry_count": retry_count,
            "last_attempted_at": None,
            "next_retry_at": None,
            "last_error": send_error,
            "fallback_reason": send_error,
            "recipient_email": recipient_email,
            "note": "任务通知已回退到平台内通知中心",
        }

    return {
        "channel": "internal",
        "status": "sent",
        "delivery_status": MAIL_STATUS_FALLBACK_INTERNAL if retry_count <= 1 else MAIL_STATUS_FAILED,
        "provider": "smtp",
        "provider_message_id": None,
        "retry_count": retry_count,
        "last_attempted_at": delivered_at,
        "next_retry_at": _compute_next_retry_at(delivered_at, max(retry_count, 1)),
        "last_error": send_error or "邮件发送失败",
        "fallback_reason": send_error or "邮件发送失败",
        "recipient_email": recipient_email,
        "note": "任务通知已回退到平台内通知中心" if retry_count <= 1 else "任务通知邮件重试失败，保留平台内通知兜底",
    }


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
    notification_result: dict[str, Any],
    delivered_at: datetime,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO internal_notification (
              tenant_id, notification_id, task_id, approval_id, customer_id, recipient_user_id,
              sender_user_id, notification_type, channel, title, content, status, delivered_at,
              delivery_status, provider, provider_message_id, retry_count, last_attempted_at,
              next_retry_at, last_error
            )
            VALUES (
              :tenant_id, :notification_id, :task_id, :approval_id, :customer_id, :recipient_user_id,
              :sender_user_id, 'task_assignment', :channel, :title, :content, :status, :delivered_at,
              :delivery_status, :provider, :provider_message_id, :retry_count, :last_attempted_at,
              :next_retry_at, :last_error
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
            "channel": notification_result["channel"],
            "title": title,
            "content": content,
            "status": notification_result["status"],
            "delivered_at": delivered_at,
            "delivery_status": notification_result["delivery_status"],
            "provider": notification_result["provider"],
            "provider_message_id": notification_result["provider_message_id"],
            "retry_count": notification_result["retry_count"],
            "last_attempted_at": notification_result["last_attempted_at"],
            "next_retry_at": notification_result["next_retry_at"],
            "last_error": notification_result["last_error"],
        },
    )


def _update_notification_delivery_state(
    db: Session,
    *,
    tenant_id: str,
    notification_id: str,
    notification_result: dict[str, Any],
) -> None:
    db.execute(
        text(
            """
            UPDATE internal_notification
            SET delivery_status = :delivery_status,
                provider = :provider,
                provider_message_id = :provider_message_id,
                retry_count = :retry_count,
                last_attempted_at = :last_attempted_at,
                next_retry_at = :next_retry_at,
                last_error = :last_error
            WHERE tenant_id = :tenant_id AND notification_id = :notification_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "notification_id": notification_id,
            "delivery_status": notification_result["delivery_status"],
            "provider": notification_result["provider"],
            "provider_message_id": notification_result["provider_message_id"],
            "retry_count": notification_result["retry_count"],
            "last_attempted_at": notification_result["last_attempted_at"],
            "next_retry_at": notification_result["next_retry_at"],
            "last_error": notification_result["last_error"],
        },
    )


def _build_notification_result_payload(
    row: dict[str, Any],
    *,
    fallback_reason: str | None = None,
    recipient_email: str | None = None,
) -> dict[str, Any]:
    result = _serialize_notification_row(row)
    if recipient_email:
        result["recipient_email"] = recipient_email
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    result["can_retry"] = result["delivery_status"] in _FAILED_DELIVERY_STATUSES
    return result


def create_task_assignment_notification(
    db: Session,
    *,
    tenant_id: str,
    approval: dict[str, Any],
    task: dict[str, Any],
    sender_user_id: str,
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：优先走真实邮件通道，失败时回退平台内通知，并记录完整投递状态。"""

    existing = db.execute(
        text(
            """
            SELECT notification_id, task_id, approval_id, customer_id, recipient_user_id, sender_user_id,
                   notification_type, channel, title, content, status, delivered_at, read_at, created_at,
                   delivery_status, provider, provider_message_id, retry_count, last_attempted_at,
                   next_retry_at, last_error
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
        return _build_notification_result_payload(row)

    delivered_at = happened_at or datetime.now()
    notification_id = new_id("notify")
    title, content = _build_task_assignment_message(approval, task)
    recipient = _load_recipient_user(db, tenant_id=tenant_id, user_id=task["assignee_user_id"])
    recipient_email = (recipient.get("email") or "").strip() if recipient else ""
    send_result: dict[str, Any] | None = None
    send_error: str | None = None
    retry_count = 0

    if recipient and recipient["status"] == 1 and recipient["is_deleted"] == 0 and recipient_email and email_service.smtp_is_configured():
        try:
            send_result = email_service.send_task_assignment_email(
                recipient_email=recipient_email,
                recipient_name=recipient.get("real_name") or recipient.get("username"),
                task=task,
                approval=approval,
            )
            retry_count = 1
        except Exception as exc:  # pragma: no cover - 失败分支由测试显式覆盖
            retry_count = 1
            send_error = str(exc)
    elif not email_service.smtp_is_configured():
        send_error = "SMTP 配置不完整，无法发送邮件"

    notification_result = _normalize_mail_attempt_result(
        delivered_at=delivered_at,
        recipient=recipient,
        recipient_email=recipient_email or None,
        send_result=send_result,
        send_error=send_error,
        retry_count=retry_count,
    )
    _insert_notification_record(
        db,
        tenant_id=tenant_id,
        notification_id=notification_id,
        task=task,
        approval=approval,
        sender_user_id=sender_user_id,
        title=title,
        content=content,
        notification_result=notification_result,
        delivered_at=delivered_at,
    )
    detail = {
        "notification_id": notification_id,
        "recipient_user_id": task["assignee_user_id"],
        "channel": notification_result["channel"],
        "title": title,
        "delivery_status": notification_result["delivery_status"],
        "retry_count": notification_result["retry_count"],
    }
    if notification_result["provider"]:
        detail["provider"] = notification_result["provider"]
    if notification_result["provider_message_id"]:
        detail["provider_message_id"] = notification_result["provider_message_id"]
    if notification_result["recipient_email"]:
        detail["recipient_email"] = notification_result["recipient_email"]
    if notification_result["fallback_reason"]:
        detail["fallback_reason"] = notification_result["fallback_reason"]
    if notification_result["next_retry_at"]:
        detail["next_retry_at"] = notification_result["next_retry_at"].isoformat()

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
        note=notification_result["note"],
        detail=detail,
        happened_at=delivered_at,
    )
    row = _load_notification_row(db, tenant_id=tenant_id, notification_id=notification_id)
    return _build_notification_result_payload(
        row,
        fallback_reason=notification_result["fallback_reason"],
        recipient_email=notification_result["recipient_email"],
    )


def get_notification_delivery_status(
    db: Session,
    *,
    current_user: dict[str, Any],
    notification_id: str,
) -> dict[str, Any]:
    row = _load_notification_row(
        db,
        tenant_id=current_user["tenant_id"],
        notification_id=notification_id,
        current_user=current_user,
    )
    return _build_notification_result_payload(row)


def list_failed_notification_deliveries(
    db: Session,
    *,
    current_user: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "limit": max(1, min(limit, 100)),
    }
    where_sql = _notification_scope_where(current_user)
    rows = db.execute(
        text(
            f"""
            SELECT n.notification_id, n.task_id, n.approval_id, n.customer_id, n.recipient_user_id, n.sender_user_id,
                   n.notification_type, n.channel, n.title, n.content, n.status, n.delivered_at, n.read_at,
                   n.created_at, n.delivery_status, n.provider, n.provider_message_id, n.retry_count,
                   n.last_attempted_at, n.next_retry_at, n.last_error
            FROM internal_notification n
            WHERE {where_sql}
              AND n.delivery_status IN ('{MAIL_STATUS_FAILED}', '{MAIL_STATUS_FALLBACK_INTERNAL}', '{MAIL_STATUS_SKIPPED}')
            ORDER BY COALESCE(n.next_retry_at, n.created_at) DESC, n.created_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_build_notification_result_payload(dict(row)) for row in rows]


def retry_notification_delivery(
    db: Session,
    *,
    current_user: dict[str, Any],
    notification_id: str,
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：失败后允许人工或 Agent 主动触发补发，先走手动重试，后续再接自动调度。"""

    notification = _load_notification_row(
        db,
        tenant_id=current_user["tenant_id"],
        notification_id=notification_id,
        current_user=current_user,
    )
    if notification["delivery_status"] in {MAIL_STATUS_SENT, MAIL_STATUS_SENT_AFTER_RETRY}:
        raise ValueError("当前通知邮件已发送成功，无需重试")

    happened_at = happened_at or datetime.now()
    recipient = _load_recipient_user(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=notification["recipient_user_id"],
    )
    recipient_email = (recipient.get("email") or "").strip() if recipient else ""
    task = _load_task_snapshot(db, tenant_id=current_user["tenant_id"], task_id=notification["task_id"])
    approval = _load_approval_snapshot(
        db,
        tenant_id=current_user["tenant_id"],
        approval_id=notification.get("approval_id"),
        customer_id=notification["customer_id"],
    )
    send_result: dict[str, Any] | None = None
    send_error: str | None = None
    retry_count = int(notification.get("retry_count") or 0)

    if recipient and recipient["status"] == 1 and recipient["is_deleted"] == 0 and recipient_email and email_service.smtp_is_configured():
        try:
            send_result = email_service.send_task_assignment_email(
                recipient_email=recipient_email,
                recipient_name=recipient.get("real_name") or recipient.get("username"),
                task=task,
                approval=approval,
            )
            retry_count += 1
        except Exception as exc:  # pragma: no cover - 失败分支由测试显式覆盖
            retry_count += 1
            send_error = str(exc)
    elif not email_service.smtp_is_configured():
        send_error = "SMTP 配置不完整，无法发送邮件"

    notification_result = _normalize_mail_attempt_result(
        delivered_at=happened_at,
        recipient=recipient,
        recipient_email=recipient_email or None,
        send_result=send_result,
        send_error=send_error,
        retry_count=retry_count,
    )
    _update_notification_delivery_state(
        db,
        tenant_id=current_user["tenant_id"],
        notification_id=notification_id,
        notification_result=notification_result,
    )
    event_detail = {
        "notification_id": notification_id,
        "delivery_status": notification_result["delivery_status"],
        "retry_count": notification_result["retry_count"],
    }
    if notification_result["provider"]:
        event_detail["provider"] = notification_result["provider"]
    if notification_result["provider_message_id"]:
        event_detail["provider_message_id"] = notification_result["provider_message_id"]
    if notification_result["fallback_reason"]:
        event_detail["fallback_reason"] = notification_result["fallback_reason"]
    if notification_result["next_retry_at"]:
        event_detail["next_retry_at"] = notification_result["next_retry_at"].isoformat()

    log_workflow_event(
        db,
        tenant_id=current_user["tenant_id"],
        entity_type="task",
        entity_id=notification["task_id"],
        approval_id=notification.get("approval_id"),
        task_id=notification["task_id"],
        customer_id=notification["customer_id"],
        risk_snapshot_id=None,
        action_type="notification_delivery_retry",
        operator_user_id=current_user["user_id"],
        note=notification_result["note"],
        detail=event_detail,
        happened_at=happened_at,
    )
    row = _load_notification_row(
        db,
        tenant_id=current_user["tenant_id"],
        notification_id=notification_id,
        current_user=current_user,
    )
    return _build_notification_result_payload(
        row,
        fallback_reason=notification_result["fallback_reason"],
        recipient_email=notification_result["recipient_email"],
    )
