import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.core.database import SessionLocal
from app.main import app


def _ensure_workflow_event_table_exists():
    with SessionLocal() as db:
        # 中文注释：测试环境可能还没手动执行最新迁移，这里补一层幂等建表，保证真实数据库集成测试可重复运行。
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
        db.commit()


def _build_headers(client: TestClient) -> tuple[dict[str, str], str]:
    login = client.post("/api/auth/login", json={"username": "manager", "password": "Manager@123456"})
    assert login.status_code == 200
    login_body = login.json()
    token = login_body["data"]["token"]
    tenant_id = login_body["data"]["user"]["tenant_id"]
    return {"Authorization": f"Bearer {token}"}, tenant_id


def _load_assignable_user_ids(tenant_id: str) -> tuple[str, list[str]]:
    with SessionLocal() as db:
        manager_user_id = db.execute(
            text(
                """
                SELECT user_id
                FROM sys_user
                WHERE tenant_id = :tenant_id AND username = 'manager' AND status = 1 AND is_deleted = 0
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id},
        ).scalar_one()
        rows = db.execute(
            text(
                """
                SELECT DISTINCT u.user_id
                FROM sys_user u
                JOIN sys_user_role ur
                  ON ur.tenant_id = u.tenant_id
                 AND ur.user_id = u.user_id
                JOIN sys_role r
                  ON r.tenant_id = ur.tenant_id
                 AND r.role_id = ur.role_id
                WHERE u.tenant_id = :tenant_id
                  AND u.status = 1
                  AND u.is_deleted = 0
                  AND r.status = 1
                  AND r.role_code IN ('owner', 'manager', 'salesperson')
                ORDER BY u.user_id ASC
                """
            ),
            {"tenant_id": tenant_id},
        ).scalars().all()
        assignable_user_ids = list(dict.fromkeys(rows))
    return manager_user_id, assignable_user_ids


def _create_temp_customer_and_approvals(
    tenant_id: str,
    owner_user_id: str,
    assignee_user_id: str,
    requested_by_user_id: str,
) -> tuple[str, list[str]]:
    customer_id = f"cust_it_{uuid4().hex[:10]}"
    approval_ids = [f"approval_it_{uuid4().hex[:10]}", f"approval_it_{uuid4().hex[:10]}"]

    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO crm_customer (
                  tenant_id, customer_id, customer_name, owner_user_id, lifecycle_stage
                )
                VALUES (
                  :tenant_id, :customer_id, :customer_name, :owner_user_id, :lifecycle_stage
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "customer_name": f"批量集成测试客户 {customer_id}",
                "owner_user_id": owner_user_id,
                "lifecycle_stage": "opportunity",
            },
        )

        for index, approval_id in enumerate(approval_ids, start=1):
            payload = {
                "assignee_user_id": assignee_user_id,
                "task_type": "quote_follow",
                "title": f"批量集成测试任务 {index}",
                "description": "用于批量审批与任务执行闭环的真实数据库集成测试",
                "priority": "high",
            }
            db.execute(
                text(
                    """
                    INSERT INTO approval_record (
                      tenant_id, approval_id, approval_type, customer_id, proposed_payload_json,
                      status, requested_by_user_id
                    )
                    VALUES (
                      :tenant_id, :approval_id, :approval_type, :customer_id, :proposed_payload_json,
                      'pending', :requested_by_user_id
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "approval_id": approval_id,
                    "approval_type": "agent_task_draft",
                    "customer_id": customer_id,
                    "proposed_payload_json": json.dumps(payload, ensure_ascii=False),
                    "requested_by_user_id": requested_by_user_id,
                },
            )
        db.commit()

    return customer_id, approval_ids


def _cleanup_temp_records(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        # 中文注释：按客户维度统一清理，避免真实数据库里遗留测试客户、审批、任务和轨迹记录。
        db.execute(
            text("DELETE FROM approval_task_event WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_follow_up_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
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
            text("DELETE FROM customer_risk_snapshot WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_batch_approval_and_task_flow_against_real_mysql():
    client = TestClient(app)
    _ensure_workflow_event_table_exists()
    headers, tenant_id = _build_headers(client)
    manager_user_id, assignable_user_ids = _load_assignable_user_ids(tenant_id)

    assert len(assignable_user_ids) >= 2, "至少需要两个可分配负责人，才能验证批量改派场景"

    initial_assignee_user_id = assignable_user_ids[0]
    reassigned_user_id = next(user_id for user_id in assignable_user_ids if user_id != initial_assignee_user_id)
    customer_id, approval_ids = _create_temp_customer_and_approvals(
        tenant_id=tenant_id,
        owner_user_id=initial_assignee_user_id,
        assignee_user_id=initial_assignee_user_id,
        requested_by_user_id=initial_assignee_user_id,
    )

    try:
        approval_response = client.post(
            "/api/approvals/batch-review",
            headers=headers,
            json={"approval_ids": approval_ids, "action": "approve"},
        )
        assert approval_response.status_code == 200
        approval_body = approval_response.json()["data"]
        assert approval_body["success_count"] == 2
        assert approval_body["failed_count"] == 0

        with SessionLocal() as db:
            task_rows = db.execute(
                text(
                    """
                    SELECT task_id, approval_id, assignee_user_id, status
                    FROM sales_task
                    WHERE tenant_id = :tenant_id AND approval_id IN :approval_ids
                    ORDER BY approval_id ASC
                    """
                ).bindparams(bindparam("approval_ids", expanding=True)),
                {"tenant_id": tenant_id, "approval_ids": approval_ids},
            ).mappings().all()
            assert len(task_rows) == 2
            task_ids = [row["task_id"] for row in task_rows]
            assert all(row["status"] == "pending" for row in task_rows)
            assert all(row["assignee_user_id"] == initial_assignee_user_id for row in task_rows)

        assign_response = client.patch(
            "/api/tasks/batch/assignee",
            headers=headers,
            json={"task_ids": task_ids, "assignee_user_id": reassigned_user_id},
        )
        assert assign_response.status_code == 200
        assign_body = assign_response.json()["data"]
        assert assign_body["success_count"] == 2
        assert assign_body["failed_count"] == 0

        status_response = client.patch(
            "/api/tasks/batch/status",
            headers=headers,
            json={
                "task_ids": task_ids,
                "status": "in_progress",
                "result_note": "真实数据库集成测试批量启动任务",
            },
        )
        assert status_response.status_code == 200
        status_body = status_response.json()["data"]
        assert status_body["success_count"] == 2
        assert status_body["failed_count"] == 0

        with SessionLocal() as db:
            updated_tasks = db.execute(
                text(
                    """
                    SELECT task_id, assignee_user_id, status
                    FROM sales_task
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    ORDER BY task_id ASC
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().all()
            assert len(updated_tasks) == 2
            assert all(row["assignee_user_id"] == reassigned_user_id for row in updated_tasks)
            assert all(row["status"] == "in_progress" for row in updated_tasks)

            event_rows = db.execute(
                text(
                    """
                    SELECT action_type, COUNT(*) AS total
                    FROM approval_task_event
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    GROUP BY action_type
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().all()
            event_counts = {row["action_type"]: row["total"] for row in event_rows}

        assert event_counts.get("approval_approved") == 2
        assert event_counts.get("task_created") == 2
        assert event_counts.get("task_reassigned") == 2
        assert event_counts.get("task_in_progress") == 2
    finally:
        _cleanup_temp_records(tenant_id, customer_id)
