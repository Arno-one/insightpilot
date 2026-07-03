from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.notification import email_service, service as notification_service


def _ensure_notification_tables_exist():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS approval_task_event (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  event_id VARCHAR(64) NOT NULL,
                  entity_type VARCHAR(20) NOT NULL,
                  entity_id VARCHAR(64) NOT NULL,
                  approval_id VARCHAR(64) NULL,
                  task_id VARCHAR(64) NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  risk_snapshot_id VARCHAR(64) NULL,
                  action_type VARCHAR(50) NOT NULL,
                  operator_user_id VARCHAR(64) NOT NULL,
                  note TEXT NULL,
                  detail_json JSON NULL,
                  happened_at DATETIME NOT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_event_id (event_id),
                  KEY idx_tenant_customer_time (tenant_id, customer_id, happened_at),
                  KEY idx_tenant_task_time (tenant_id, task_id, happened_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS internal_notification (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  notification_id VARCHAR(64) NOT NULL,
                  task_id VARCHAR(64) NOT NULL,
                  approval_id VARCHAR(64) NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  recipient_user_id VARCHAR(64) NOT NULL,
                  sender_user_id VARCHAR(64) NOT NULL,
                  notification_type VARCHAR(50) NOT NULL,
                  channel VARCHAR(30) NOT NULL DEFAULT 'internal',
                  title VARCHAR(150) NOT NULL,
                  content TEXT NOT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'sent',
                  delivered_at DATETIME NULL,
                  read_at DATETIME NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_notification_id (notification_id),
                  UNIQUE KEY uk_task_recipient_type (tenant_id, task_id, recipient_user_id, notification_type),
                  KEY idx_tenant_task (tenant_id, task_id),
                  KEY idx_tenant_customer (tenant_id, customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _build_fixture() -> tuple[str, dict[str, str], dict[str, str], str]:
    tenant_id = "demo_tenant"
    approval_id = f"approval_notify_{uuid4().hex[:10]}"
    customer_id = f"customer_notify_{uuid4().hex[:10]}"
    task_id = f"task_notify_{uuid4().hex[:10]}"
    approval = {
        "tenant_id": tenant_id,
        "approval_id": approval_id,
        "customer_id": customer_id,
    }
    task = {
        "task_id": task_id,
        "assignee_user_id": "u_manager_001",
        "title": "邮件通知测试任务",
        "description": "验证任务通知邮件发送与回退逻辑",
        "priority": "high",
        "due_at": "2026-07-05T10:00:00",
    }
    return tenant_id, approval, task, customer_id


def _cleanup_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM approval_task_event WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM internal_notification WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_create_task_assignment_notification_prefers_email(monkeypatch):
    _ensure_notification_tables_exist()
    tenant_id, approval, task, customer_id = _build_fixture()
    captured: list[dict[str, str]] = []

    def _fake_send(**kwargs):
        captured.append(kwargs)
        return {
            "provider": "smtp",
            "sender_email": "no-reply@insightpilot.local",
            "recipient_email": kwargs["recipient_email"],
            "recipient_name": kwargs.get("recipient_name"),
            "subject": "mock-subject",
        }

    monkeypatch.setattr(email_service, "send_task_assignment_email", _fake_send)

    try:
        with SessionLocal() as db:
            result = notification_service.create_task_assignment_notification(
                db,
                tenant_id=tenant_id,
                approval=approval,
                task=task,
                sender_user_id="u_owner_001",
            )
            db.commit()

        with SessionLocal() as db:
            row = db.execute(
                text(
                    """
                    SELECT channel, title, status
                    FROM internal_notification
                    WHERE tenant_id = :tenant_id AND task_id = :task_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "task_id": task["task_id"]},
            ).mappings().first()

        assert captured and captured[0]["recipient_email"] == "manager@insightpilot.local"
        assert result["channel"] == "email"
        assert result["recipient_email"] == "manager@insightpilot.local"
        assert "fallback_reason" not in result
        assert row is not None
        assert row["channel"] == "email"
        assert row["status"] == "sent"
    finally:
        _cleanup_fixture(tenant_id, customer_id)


def test_create_task_assignment_notification_falls_back_to_internal(monkeypatch):
    _ensure_notification_tables_exist()
    tenant_id, approval, task, customer_id = _build_fixture()

    def _raise_send(**kwargs):
        raise RuntimeError("SMTP service unavailable")

    monkeypatch.setattr(email_service, "send_task_assignment_email", _raise_send)

    try:
        with SessionLocal() as db:
            result = notification_service.create_task_assignment_notification(
                db,
                tenant_id=tenant_id,
                approval=approval,
                task=task,
                sender_user_id="u_owner_001",
            )
            db.commit()

        with SessionLocal() as db:
            row = db.execute(
                text(
                    """
                    SELECT channel, status
                    FROM internal_notification
                    WHERE tenant_id = :tenant_id AND task_id = :task_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "task_id": task["task_id"]},
            ).mappings().first()
            event = db.execute(
                text(
                    """
                    SELECT note
                    FROM approval_task_event
                    WHERE tenant_id = :tenant_id AND task_id = :task_id AND action_type = 'notification_sent'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "task_id": task["task_id"]},
            ).mappings().first()

        assert result["channel"] == "internal"
        assert "SMTP service unavailable" in result["fallback_reason"]
        assert row is not None
        assert row["channel"] == "internal"
        assert row["status"] == "sent"
        assert event is not None
        assert "回退" in event["note"]
    finally:
        _cleanup_fixture(tenant_id, customer_id)
