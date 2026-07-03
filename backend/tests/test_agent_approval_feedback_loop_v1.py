import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.core.database import SessionLocal
from app.main import app


def _ensure_workflow_event_table_exists():
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


def _create_agent_run_feedback_fixture(tenant_id: str, requester_user_id: str) -> tuple[str, str, list[str], list[str]]:
    run_id = f"run_feedback_{uuid4().hex[:10]}"
    customer_ids = [f"cust_feedback_{uuid4().hex[:10]}", f"cust_feedback_{uuid4().hex[:10]}"]
    approval_ids = [f"appr_feedback_{uuid4().hex[:10]}", f"appr_feedback_{uuid4().hex[:10]}"]
    risk_snapshot_ids = [f"risk_feedback_{uuid4().hex[:10]}", f"risk_feedback_{uuid4().hex[:10]}"]

    with SessionLocal() as db:
        for index, customer_id in enumerate(customer_ids):
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
                    "customer_name": f"审批回写测试客户 {index + 1}",
                    "owner_user_id": requester_user_id,
                },
            )

        output_json = {
            "risk_count": 2,
            "approval_count": 2,
            "items": [
                {
                    "approval_id": approval_ids[0],
                    "customer_id": customer_ids[0],
                    "risk_snapshot_id": risk_snapshot_ids[0],
                    "risk_score": 82,
                    "risk_level": "high",
                    "review_summary": "需要人工确认是否升级处理",
                },
                {
                    "approval_id": approval_ids[1],
                    "customer_id": customer_ids[1],
                    "risk_snapshot_id": risk_snapshot_ids[1],
                    "risk_score": 71,
                    "risk_level": "medium",
                    "review_summary": "建议继续观察并补充上下文",
                },
            ],
        }
        db.execute(
            text(
                """
                INSERT INTO agent_run (
                  tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json, status, started_at
                )
                VALUES (
                  :tenant_id, :run_id, :user_id, 'risk_analysis', 'risk_analysis_graph',
                  :input_json, :output_json, 'awaiting_approval', NOW()
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "user_id": requester_user_id,
                "input_json": json.dumps({"scope": "tenant"}, ensure_ascii=False),
                "output_json": json.dumps(output_json, ensure_ascii=False),
            },
        )

        for index, approval_id in enumerate(approval_ids):
            payload = {
                "assignee_user_id": requester_user_id,
                "task_type": "quote_follow",
                "title": f"审批回写任务 {index + 1}",
                "description": "用于验证审批结果回写 Agent Run。",
                "priority": "high",
            }
            db.execute(
                text(
                    """
                    INSERT INTO customer_risk_snapshot (
                      tenant_id, risk_snapshot_id, customer_id, owner_user_id, risk_score, risk_level,
                      rule_hits_json, evidence_json, llm_reason, llm_suggestion, suggested_task_json,
                      status, generated_by_run_id
                    )
                    VALUES (
                      :tenant_id, :risk_snapshot_id, :customer_id, :owner_user_id, :risk_score, :risk_level,
                      '[]', '{}', '测试原因', '测试建议', :suggested_task_json, 'pending_review', :generated_by_run_id
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "risk_snapshot_id": risk_snapshot_ids[index],
                    "customer_id": customer_ids[index],
                    "owner_user_id": requester_user_id,
                    "risk_score": 82 if index == 0 else 71,
                    "risk_level": "high" if index == 0 else "medium",
                    "suggested_task_json": json.dumps(payload, ensure_ascii=False),
                    "generated_by_run_id": run_id,
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO approval_record (
                      tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id,
                      proposed_payload_json, status, requested_by_user_id
                    )
                    VALUES (
                      :tenant_id, :approval_id, 'agent_task_draft', :run_id, :risk_snapshot_id, :customer_id,
                      :proposed_payload_json, 'pending', :requested_by_user_id
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "approval_id": approval_id,
                    "run_id": run_id,
                    "risk_snapshot_id": risk_snapshot_ids[index],
                    "customer_id": customer_ids[index],
                    "proposed_payload_json": json.dumps(payload, ensure_ascii=False),
                    "requested_by_user_id": requester_user_id,
                },
            )
        db.commit()

    return run_id, requester_user_id, customer_ids, approval_ids


def _cleanup_agent_run_feedback_fixture(tenant_id: str, run_id: str, customer_ids: list[str]):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM approval_task_event WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.execute(
            text("DELETE FROM internal_notification WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.execute(
            text("DELETE FROM internal_calendar_event WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.execute(
            text("DELETE FROM sales_task WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.execute(
            text("DELETE FROM approval_record WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.execute(
            text("DELETE FROM customer_risk_snapshot WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.execute(
            text("DELETE FROM agent_run WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id IN :customer_ids").bindparams(
                bindparam("customer_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "customer_ids": customer_ids},
        )
        db.commit()


def test_agent_run_feedback_loop_updates_output_and_status():
    client = TestClient(app)
    _ensure_workflow_event_table_exists()
    headers, tenant_id, requester_user_id = _build_headers(client)
    run_id, _, customer_ids, approval_ids = _create_agent_run_feedback_fixture(tenant_id, requester_user_id)

    try:
        approve_response = client.post(f"/api/approvals/{approval_ids[0]}/approve", headers=headers)
        assert approve_response.status_code == 200

        with SessionLocal() as db:
            run_row = db.execute(
                text(
                    """
                    SELECT status, output_json
                    FROM agent_run
                    WHERE tenant_id = :tenant_id AND run_id = :run_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run_id},
            ).mappings().first()
            assert run_row is not None
            output = json.loads(run_row["output_json"])
            approved_item = next(item for item in output["items"] if item["approval_id"] == approval_ids[0])
            pending_item = next(item for item in output["items"] if item["approval_id"] == approval_ids[1])

        assert run_row["status"] == "awaiting_approval"
        assert approved_item["approval_status"] == "approved"
        assert approved_item["task_id"]
        assert approved_item["human_review"]["reviewer_user_id"] == requester_user_id
        assert len(approved_item["human_review"]["tool_calling_records"]) == 3
        assert pending_item.get("approval_status") is None
        assert output["approval_summary"]["approved_count"] == 1
        assert output["approval_summary"]["pending_count"] == 1
        assert output["approval_summary"]["converted_task_count"] == 1

        reject_response = client.post(
            f"/api/approvals/{approval_ids[1]}/reject",
            headers=headers,
            json={"review_comment": "当前证据不足，先不下发"},
        )
        assert reject_response.status_code == 200

        with SessionLocal() as db:
            final_run_row = db.execute(
                text(
                    """
                    SELECT status, output_json
                    FROM agent_run
                    WHERE tenant_id = :tenant_id AND run_id = :run_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "run_id": run_id},
            ).mappings().first()
            assert final_run_row is not None
            final_output = json.loads(final_run_row["output_json"])
            rejected_item = next(item for item in final_output["items"] if item["approval_id"] == approval_ids[1])

        assert final_run_row["status"] == "success"
        assert rejected_item["approval_status"] == "rejected"
        assert rejected_item["review_comment"] == "当前证据不足，先不下发"
        assert rejected_item["human_review"]["task_id"] is None
        assert final_output["approval_summary"]["approved_count"] == 1
        assert final_output["approval_summary"]["rejected_count"] == 1
        assert final_output["approval_summary"]["pending_count"] == 0
        assert final_output["approval_summary"]["all_reviewed"] is True
    finally:
        _cleanup_agent_run_feedback_fixture(tenant_id, run_id, customer_ids)
