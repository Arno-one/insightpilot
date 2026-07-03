from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
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
                  delivery_status VARCHAR(30) NOT NULL DEFAULT 'pending',
                  provider VARCHAR(30) NULL,
                  provider_message_id VARCHAR(128) NULL,
                  retry_count INT NOT NULL DEFAULT 0,
                  last_attempted_at DATETIME NULL,
                  next_retry_at DATETIME NULL,
                  last_error TEXT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_notification_id (notification_id),
                  UNIQUE KEY uk_task_recipient_type (tenant_id, task_id, recipient_user_id, notification_type),
                  KEY idx_tenant_task (tenant_id, task_id),
                  KEY idx_tenant_customer (tenant_id, customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        existing_columns = set(db.execute(text("SHOW COLUMNS FROM internal_notification")).scalars().all())
        missing_columns = [
            ("delivery_status", "ALTER TABLE internal_notification ADD COLUMN delivery_status VARCHAR(30) NOT NULL DEFAULT 'pending'"),
            ("provider", "ALTER TABLE internal_notification ADD COLUMN provider VARCHAR(30) NULL"),
            ("provider_message_id", "ALTER TABLE internal_notification ADD COLUMN provider_message_id VARCHAR(128) NULL"),
            ("retry_count", "ALTER TABLE internal_notification ADD COLUMN retry_count INT NOT NULL DEFAULT 0"),
            ("last_attempted_at", "ALTER TABLE internal_notification ADD COLUMN last_attempted_at DATETIME NULL"),
            ("next_retry_at", "ALTER TABLE internal_notification ADD COLUMN next_retry_at DATETIME NULL"),
            ("last_error", "ALTER TABLE internal_notification ADD COLUMN last_error TEXT NULL"),
        ]
        for column_name, alter_sql in missing_columns:
            if column_name not in existing_columns:
                db.execute(text(alter_sql))
        db.commit()


def _build_headers(client: TestClient) -> tuple[dict[str, str], str]:
    login = client.post("/api/auth/login", json={"username": "manager", "password": "Manager@123456"})
    assert login.status_code == 200
    login_body = login.json()["data"]
    return {"Authorization": f"Bearer {login_body['token']}"}, login_body["user"]["tenant_id"]


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
        "description": "验证任务通知邮件发送、状态查询与失败重试",
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
        db.execute(
            text("DELETE FROM sales_task WHERE tenant_id = :tenant_id AND task_id LIKE 'task_notify_%'"),
            {"tenant_id": tenant_id},
        )
        db.execute(
            text("DELETE FROM approval_record WHERE tenant_id = :tenant_id AND approval_id LIKE 'approval_notify_%'"),
            {"tenant_id": tenant_id},
        )
        db.commit()


def _ensure_task_and_approval_records(tenant_id: str, approval: dict[str, str], task: dict[str, str]):
    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT IGNORE INTO approval_record (
                  tenant_id, approval_id, approval_type, customer_id, proposed_payload_json, status, requested_by_user_id
                )
                VALUES (
                  :tenant_id, :approval_id, 'agent_task_draft', :customer_id, '{}', 'approved', 'u_owner_001'
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "approval_id": approval["approval_id"],
                "customer_id": approval["customer_id"],
            },
        )
        db.execute(
            text(
                """
                INSERT IGNORE INTO sales_task (
                  tenant_id, task_id, approval_id, customer_id, assignee_user_id, creator_user_id,
                  task_type, title, description, priority, status, due_at
                )
                VALUES (
                  :tenant_id, :task_id, :approval_id, :customer_id, :assignee_user_id, 'u_owner_001',
                  'quote_follow', :title, :description, :priority, 'pending', NOW()
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "task_id": task["task_id"],
                "approval_id": approval["approval_id"],
                "customer_id": approval["customer_id"],
                "assignee_user_id": task["assignee_user_id"],
                "title": task["title"],
                "description": task["description"],
                "priority": task["priority"],
            },
        )
        db.commit()


def test_create_task_assignment_notification_prefers_email(monkeypatch):
    _ensure_notification_tables_exist()
    tenant_id, approval, task, customer_id = _build_fixture()
    _ensure_task_and_approval_records(tenant_id, approval, task)
    captured: list[dict[str, str]] = []

    def _fake_send(**kwargs):
        captured.append(kwargs)
        return {
            "provider": "smtp",
            "sender_email": "no-reply@insightpilot.local",
            "recipient_email": kwargs["recipient_email"],
            "recipient_name": kwargs.get("recipient_name"),
            "subject": "mock-subject",
            "provider_message_id": "<mock-success@insightpilot.local>",
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
                    SELECT channel, status, delivery_status, provider, provider_message_id, retry_count, last_error
                    FROM internal_notification
                    WHERE tenant_id = :tenant_id AND task_id = :task_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "task_id": task["task_id"]},
            ).mappings().first()

        assert captured and captured[0]["recipient_email"] == "manager@insightpilot.local"
        assert result["channel"] == "email"
        assert result["delivery_status"] == "sent"
        assert result["recipient_email"] == "manager@insightpilot.local"
        assert result["retry_count"] == 1
        assert result["provider_message_id"] == "<mock-success@insightpilot.local>"
        assert "fallback_reason" not in result
        assert row is not None
        assert row["channel"] == "email"
        assert row["status"] == "sent"
        assert row["delivery_status"] == "sent"
        assert row["provider"] == "smtp"
        assert row["retry_count"] == 1
        assert row["last_error"] is None
    finally:
        _cleanup_fixture(tenant_id, customer_id)


def test_create_task_assignment_notification_falls_back_to_internal(monkeypatch):
    _ensure_notification_tables_exist()
    tenant_id, approval, task, customer_id = _build_fixture()
    _ensure_task_and_approval_records(tenant_id, approval, task)

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
                    SELECT channel, status, delivery_status, retry_count, next_retry_at, last_error
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
        assert result["delivery_status"] == "fallback_internal"
        assert result["retry_count"] == 1
        assert "SMTP service unavailable" in result["fallback_reason"]
        assert row is not None
        assert row["channel"] == "internal"
        assert row["status"] == "sent"
        assert row["delivery_status"] == "fallback_internal"
        assert row["retry_count"] == 1
        assert row["next_retry_at"] is not None
        assert "SMTP service unavailable" in row["last_error"]
        assert event is not None
        assert "回退" in event["note"]
    finally:
        _cleanup_fixture(tenant_id, customer_id)


def test_retry_notification_delivery_succeeds_after_fallback(monkeypatch):
    _ensure_notification_tables_exist()
    tenant_id, approval, task, customer_id = _build_fixture()
    _ensure_task_and_approval_records(tenant_id, approval, task)

    def _raise_send(**kwargs):
        raise RuntimeError("SMTP service unavailable")

    monkeypatch.setattr(email_service, "send_task_assignment_email", _raise_send)

    try:
        with SessionLocal() as db:
            created = notification_service.create_task_assignment_notification(
                db,
                tenant_id=tenant_id,
                approval=approval,
                task=task,
                sender_user_id="u_owner_001",
            )
            db.commit()

        monkeypatch.setattr(
            email_service,
            "send_task_assignment_email",
            lambda **kwargs: {
                "provider": "smtp",
                "sender_email": "no-reply@insightpilot.local",
                "recipient_email": kwargs["recipient_email"],
                "recipient_name": kwargs.get("recipient_name"),
                "subject": "mock-retry-subject",
                "provider_message_id": "<mock-retry@insightpilot.local>",
            },
        )

        with SessionLocal() as db:
            current_user = notification_service.load_notification_operator_context(
                db,
                tenant_id=tenant_id,
                user_id="u_manager_001",
            )
            retried = notification_service.retry_notification_delivery(
                db,
                current_user=current_user,
                notification_id=created["notification_id"],
            )
            db.commit()

        with SessionLocal() as db:
            row = db.execute(
                text(
                    """
                    SELECT delivery_status, retry_count, provider_message_id, next_retry_at, last_error
                    FROM internal_notification
                    WHERE tenant_id = :tenant_id AND notification_id = :notification_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "notification_id": created["notification_id"]},
            ).mappings().first()

        assert retried["delivery_status"] == "sent_after_retry"
        assert retried["retry_count"] == 2
        assert retried["provider_message_id"] == "<mock-retry@insightpilot.local>"
        assert row is not None
        assert row["delivery_status"] == "sent_after_retry"
        assert row["retry_count"] == 2
        assert row["next_retry_at"] is None
        assert row["last_error"] is None
    finally:
        _cleanup_fixture(tenant_id, customer_id)


def test_notification_router_supports_failed_list_and_retry(monkeypatch):
    _ensure_notification_tables_exist()
    tenant_id, approval, task, customer_id = _build_fixture()
    _ensure_task_and_approval_records(tenant_id, approval, task)

    def _raise_send(**kwargs):
        raise RuntimeError("SMTP service unavailable")

    monkeypatch.setattr(email_service, "send_task_assignment_email", _raise_send)
    client = TestClient(app)
    headers, _ = _build_headers(client)

    try:
        with SessionLocal() as db:
            created = notification_service.create_task_assignment_notification(
                db,
                tenant_id=tenant_id,
                approval=approval,
                task=task,
                sender_user_id="u_owner_001",
            )
            db.commit()

        failed_response = client.get("/api/notifications/failed?limit=10", headers=headers)
        assert failed_response.status_code == 200
        failed_items = failed_response.json()["data"]
        target = next(item for item in failed_items if item["notification_id"] == created["notification_id"])
        assert target["delivery_status"] == "fallback_internal"

        monkeypatch.setattr(
            email_service,
            "send_task_assignment_email",
            lambda **kwargs: {
                "provider": "smtp",
                "sender_email": "no-reply@insightpilot.local",
                "recipient_email": kwargs["recipient_email"],
                "recipient_name": kwargs.get("recipient_name"),
                "subject": "mock-retry-subject",
                "provider_message_id": "<mock-router-retry@insightpilot.local>",
            },
        )

        retry_response = client.post(f"/api/notifications/{created['notification_id']}/retry", headers=headers)
        assert retry_response.status_code == 200
        retry_body = retry_response.json()["data"]
        assert retry_body["delivery_status"] == "sent_after_retry"

        detail_response = client.get(f"/api/notifications/{created['notification_id']}", headers=headers)
        assert detail_response.status_code == 200
        detail_body = detail_response.json()["data"]
        assert detail_body["delivery_status"] == "sent_after_retry"
        assert detail_body["retry_count"] == 2
    finally:
        _cleanup_fixture(tenant_id, customer_id)
