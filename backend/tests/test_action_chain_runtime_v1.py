from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.calendar import service as calendar_service
from app.modules.notification import email_service


def _ensure_action_chain_tables_exist():
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
                  KEY idx_tenant_approval_time (tenant_id, approval_id, happened_at),
                  KEY idx_tenant_task_time (tenant_id, task_id, happened_at),
                  KEY idx_tenant_entity_time (tenant_id, entity_type, entity_id, happened_at)
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
                  KEY idx_tenant_recipient_status (tenant_id, recipient_user_id, status),
                  KEY idx_tenant_task (tenant_id, task_id),
                  KEY idx_tenant_customer (tenant_id, customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS internal_calendar_event (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  event_id VARCHAR(64) NOT NULL,
                  task_id VARCHAR(64) NOT NULL,
                  approval_id VARCHAR(64) NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  owner_user_id VARCHAR(64) NOT NULL,
                  title VARCHAR(150) NOT NULL,
                  description TEXT NULL,
                  start_at DATETIME NOT NULL,
                  end_at DATETIME NOT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'scheduled',
                  created_by_user_id VARCHAR(64) NOT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_event_id (event_id),
                  UNIQUE KEY uk_task_owner (tenant_id, task_id, owner_user_id),
                  KEY idx_tenant_owner_start (tenant_id, owner_user_id, start_at),
                  KEY idx_tenant_task (tenant_id, task_id),
                  KEY idx_tenant_customer (tenant_id, customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_action_run (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  action_run_id VARCHAR(64) NOT NULL,
                  chain_code VARCHAR(64) NOT NULL,
                  approval_id VARCHAR(64) NULL,
                  customer_id VARCHAR(64) NULL,
                  trigger_source VARCHAR(50) NOT NULL DEFAULT 'approval',
                  triggered_by_user_id VARCHAR(64) NOT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'running',
                  current_step_code VARCHAR(64) NULL,
                  context_payload_json JSON NULL,
                  error_message TEXT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  finished_at DATETIME NULL,
                  UNIQUE KEY uk_action_run_id (action_run_id),
                  KEY idx_tenant_status_created (tenant_id, status, created_at),
                  KEY idx_tenant_approval_created (tenant_id, approval_id, created_at),
                  KEY idx_tenant_customer_created (tenant_id, customer_id, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_action_run_step (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  step_run_id VARCHAR(64) NOT NULL,
                  action_run_id VARCHAR(64) NOT NULL,
                  approval_id VARCHAR(64) NULL,
                  customer_id VARCHAR(64) NULL,
                  step_code VARCHAR(64) NOT NULL,
                  tool_name VARCHAR(120) NOT NULL,
                  step_order INT NOT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'running',
                  input_payload_json JSON NULL,
                  output_payload_json JSON NULL,
                  error_message TEXT NULL,
                  retry_count INT NOT NULL DEFAULT 0,
                  started_at DATETIME NULL,
                  finished_at DATETIME NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_step_run_id (step_run_id),
                  UNIQUE KEY uk_action_run_step (tenant_id, action_run_id, step_code),
                  KEY idx_tenant_action_run (tenant_id, action_run_id, step_order),
                  KEY idx_tenant_status_created (tenant_id, status, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _build_headers(client: TestClient) -> tuple[dict[str, str], str, str]:
    login = client.post("/api/auth/login", json={"username": "manager", "password": "Manager@123456"})
    assert login.status_code == 200
    login_body = login.json()["data"]
    return (
        {"Authorization": f"Bearer {login_body['token']}"},
        login_body["user"]["tenant_id"],
        login_body["user"]["user_id"],
    )


def _create_temp_approval(tenant_id: str, owner_user_id: str, requested_by_user_id: str) -> tuple[str, str]:
    customer_id = f"cust_chain_{uuid4().hex[:10]}"
    approval_id = f"appr_chain_{uuid4().hex[:10]}"
    payload = {
        "assignee_user_id": owner_user_id,
        "task_type": "quote_follow",
        "title": "动作链失败恢复测试任务",
        "description": "用于验证审批后动作链运行记录、失败恢复与重试能力。",
        "priority": "high",
    }
    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO crm_customer (
                  tenant_id, customer_id, customer_name, owner_user_id, lifecycle_stage
                )
                VALUES (
                  :tenant_id, :customer_id, :customer_name, :owner_user_id, 'opportunity'
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "customer_name": f"动作链测试客户 {customer_id}",
                "owner_user_id": owner_user_id,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO approval_record (
                  tenant_id, approval_id, approval_type, customer_id, proposed_payload_json,
                  status, requested_by_user_id
                )
                VALUES (
                  :tenant_id, :approval_id, 'agent_task_draft', :customer_id, :proposed_payload_json,
                  'pending', :requested_by_user_id
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "approval_id": approval_id,
                "customer_id": customer_id,
                "proposed_payload_json": json.dumps(payload, ensure_ascii=False),
                "requested_by_user_id": requested_by_user_id,
            },
        )
        db.commit()
    return customer_id, approval_id


def _cleanup_temp_records(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM approval_task_event WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM agent_action_run_step WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM agent_action_run WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM internal_notification WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM internal_calendar_event WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM sales_task WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM approval_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_action_chain_runtime_supports_failed_step_resume(monkeypatch):
    client = TestClient(app)
    _ensure_action_chain_tables_exist()
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, approval_id = _create_temp_approval(tenant_id, user_id, user_id)
    original_create_calendar_event = calendar_service.create_follow_up_calendar_event
    calendar_call_count = {"value": 0}

    monkeypatch.setattr(
        email_service,
        "send_task_assignment_email",
        lambda **kwargs: {
            "provider": "smtp",
            "sender_email": "no-reply@insightpilot.local",
            "recipient_email": kwargs["recipient_email"],
            "recipient_name": kwargs.get("recipient_name"),
            "subject": f"mock:{kwargs['task']['title']}",
            "provider_message_id": "<mock-action-chain@insightpilot.local>",
        },
    )

    def _flaky_calendar(*args, **kwargs):
        calendar_call_count["value"] += 1
        if calendar_call_count["value"] == 1:
            raise RuntimeError("calendar provider temporarily unavailable")
        return original_create_calendar_event(*args, **kwargs)

    monkeypatch.setattr(calendar_service, "create_follow_up_calendar_event", _flaky_calendar)

    try:
        approve_response = client.post(f"/api/approvals/{approval_id}/approve", headers=headers)
        assert approve_response.status_code == 200
        approve_body = approve_response.json()["data"]
        action_run_id = approve_body["action_run_id"]
        assert approve_body["task_id"]
        assert approve_body["action_status"] == "failed"

        failed_response = client.get("/api/approvals/action-runs/failed?limit=10", headers=headers)
        assert failed_response.status_code == 200
        failed_items = failed_response.json()["data"]
        failed_item = next(item for item in failed_items if item["action_run_id"] == action_run_id)
        assert failed_item["current_step_code"] == "create_calendar_event"
        assert failed_item["can_retry"] is True

        detail_response = client.get(f"/api/approvals/action-runs/{action_run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail_body = detail_response.json()["data"]
        assert detail_body["status"] == "failed"
        assert detail_body["current_step_code"] == "create_calendar_event"
        assert detail_body["recovery_plan"]["retry_mode"] == "resume_from_failed_step"
        assert detail_body["recovery_plan"]["failed_step_code"] == "create_calendar_event"
        assert detail_body["recovery_plan"]["compensation_items"][0]["strategy"] == "reuse_success_output"
        assert len(detail_body["tool_executions"]) == 3
        assert detail_body["tool_executions"][-1]["status"] == "failed"
        assert "calendar provider temporarily unavailable" in detail_body["tool_executions"][-1]["error_message"]

        retry_response = client.post(f"/api/approvals/action-runs/{action_run_id}/retry", headers=headers)
        assert retry_response.status_code == 200
        retry_body = retry_response.json()["data"]
        assert retry_body["status"] == "success"
        assert retry_body["recovery_plan"] is None
        assert retry_body["calendar_event"]["event_id"]
        assert retry_body["tool_executions"][-1]["status"] == "success"

        with SessionLocal() as db:
            run_row = db.execute(
                text(
                    """
                    SELECT status, current_step_code, error_message
                    FROM agent_action_run
                    WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "action_run_id": action_run_id},
            ).mappings().first()
            step_row = db.execute(
                text(
                    """
                    SELECT status, retry_count, error_message
                    FROM agent_action_run_step
                    WHERE tenant_id = :tenant_id
                      AND action_run_id = :action_run_id
                      AND step_code = 'create_calendar_event'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "action_run_id": action_run_id},
            ).mappings().first()
            task_count = db.execute(
                text(
                    """
                    SELECT COUNT(1)
                    FROM sales_task
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).scalar_one()
            notification_count = db.execute(
                text(
                    """
                    SELECT COUNT(1)
                    FROM internal_notification
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).scalar_one()
            calendar_count = db.execute(
                text(
                    """
                    SELECT COUNT(1)
                    FROM internal_calendar_event
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).scalar_one()

        assert run_row is not None
        assert run_row["status"] == "success"
        assert run_row["current_step_code"] is None
        assert run_row["error_message"] is None
        assert step_row is not None
        assert step_row["status"] == "success"
        assert step_row["retry_count"] == 2
        assert step_row["error_message"] is None
        assert task_count == 1
        assert notification_count == 1
        assert calendar_count == 1
    finally:
        _cleanup_temp_records(tenant_id, customer_id)
