import json
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.core.database import SessionLocal
from app.main import app
from app.modules.agent.graphs.risk_analysis_graph import run_risk_analysis_workflow
from app.modules.llm import client as llm_client


def _loads_json(value):
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _ensure_approval_task_event_table_exists():
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
        db.commit()


def _ensure_customer_memory_table_exists():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS customer_memory (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  memory_id VARCHAR(64) NOT NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer',
                  summary_text TEXT NOT NULL,
                  summary_json JSON NULL,
                  source_run_id VARCHAR(64) NULL,
                  last_compiled_at DATETIME NOT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_memory_id (memory_id),
                  UNIQUE KEY uk_tenant_customer_scope (tenant_id, customer_id, memory_scope),
                  KEY idx_tenant_customer (tenant_id, customer_id),
                  KEY idx_tenant_compiled_at (tenant_id, last_compiled_at),
                  KEY idx_source_run_id (source_run_id)
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


def _create_customer_memory_fixture(tenant_id: str, user_id: str) -> tuple[str, str, str]:
    customer_id = f"cust_mem_{uuid4().hex[:10]}"
    deal_id = f"deal_mem_{uuid4().hex[:10]}"
    report_id = f"report_mem_{uuid4().hex[:10]}"
    now = datetime.now()

    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO crm_customer (
                  tenant_id, customer_id, customer_name, owner_user_id, lifecycle_stage, intent_level,
                  customer_level, competitor_involved, next_follow_up_at, last_follow_up_at, last_sentiment
                )
                VALUES (
                  :tenant_id, :customer_id, :customer_name, :owner_user_id, 'opportunity', 'high',
                  'A', 1, NULL, :last_follow_up_at, 'negative'
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "customer_name": "客户记忆专项测试客户",
                "owner_user_id": user_id,
                "last_follow_up_at": now - timedelta(days=35),
            },
        )
        db.execute(
            text(
                """
                INSERT INTO crm_deal (
                  tenant_id, deal_id, customer_id, owner_user_id, deal_name, stage, amount,
                  quote_amount, quoted_at, expected_close_at, close_result
                )
                VALUES (
                  :tenant_id, :deal_id, :customer_id, :owner_user_id, :deal_name, 'quotation', 120000,
                  118000, :quoted_at, :expected_close_at, 'open'
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "deal_id": deal_id,
                "customer_id": customer_id,
                "owner_user_id": user_id,
                "deal_name": "客户记忆专项测试商机",
                "quoted_at": now - timedelta(days=18),
                "expected_close_at": date.today() + timedelta(days=12),
            },
        )
        db.execute(
            text(
                """
                INSERT INTO crm_follow_up_record (
                  tenant_id, follow_up_id, customer_id, deal_id, owner_user_id, follow_up_type,
                  content, sentiment, customer_feedback, next_action, next_follow_up_at, occurred_at
                )
                VALUES (
                  :tenant_id, :follow_up_id, :customer_id, :deal_id, :owner_user_id, 'wechat',
                  :content, 'negative', :customer_feedback, :next_action, NULL, :occurred_at
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "follow_up_id": f"fu_mem_{uuid4().hex[:10]}",
                "customer_id": customer_id,
                "deal_id": deal_id,
                "owner_user_id": user_id,
                "content": "客户反馈暂时不急，正在对比竞品方案。",
                "customer_feedback": "客户反馈预算和方案都在比较中",
                "next_action": "主管协助判断是否需要升级跟进",
                "occurred_at": now - timedelta(days=35),
            },
        )
        db.execute(
            text(
                """
                INSERT INTO business_report (
                  tenant_id, report_id, run_id, report_type, report_date, summary, metrics_json,
                  risk_top_json, suggestions, created_by_user_id
                )
                VALUES (
                  :tenant_id, :report_id, NULL, 'daily', :report_date, :summary, :metrics_json,
                  :risk_top_json, :suggestions, :created_by_user_id
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "report_id": report_id,
                "report_date": date.today(),
                "summary": "该客户连续两周推进放缓，竞品介入迹象明显，建议主管提前介入。",
                "metrics_json": json.dumps({}, ensure_ascii=False),
                "risk_top_json": json.dumps(
                    [{"customer_id": customer_id, "customer_name": "客户记忆专项测试客户"}],
                    ensure_ascii=False,
                ),
                "suggestions": "优先核对真实采购节奏和竞品压价情况。",
                "created_by_user_id": user_id,
            },
        )
        db.commit()

    return customer_id, deal_id, report_id


def _cleanup_customer_memory_fixture(tenant_id: str, customer_id: str, deal_id: str, report_id: str, run_ids: list[str]):
    with SessionLocal() as db:
        if run_ids:
            db.execute(
                text("DELETE FROM agent_step WHERE tenant_id = :tenant_id AND run_id IN :run_ids").bindparams(
                    bindparam("run_ids", expanding=True)
                ),
                {"tenant_id": tenant_id, "run_ids": run_ids},
            )
            db.execute(
                text("DELETE FROM agent_run WHERE tenant_id = :tenant_id AND run_id IN :run_ids").bindparams(
                    bindparam("run_ids", expanding=True)
                ),
                {"tenant_id": tenant_id, "run_ids": run_ids},
            )
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM approval_task_event WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
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
            text("DELETE FROM business_report WHERE tenant_id = :tenant_id AND report_id = :report_id"),
            {"tenant_id": tenant_id, "report_id": report_id},
        )
        db.execute(
            text("DELETE FROM crm_follow_up_record WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_deal WHERE tenant_id = :tenant_id AND deal_id = :deal_id"),
            {"tenant_id": tenant_id, "deal_id": deal_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_customer_memory_is_written_and_reused_by_risk_agent(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")
    _ensure_approval_task_event_table_exists()
    _ensure_customer_memory_table_exists()
    _, tenant_id, user_id = _build_headers(client)
    customer_id, deal_id, report_id = _create_customer_memory_fixture(tenant_id, user_id)
    run_ids: list[str] = []

    try:
        first_run = run_risk_analysis_workflow(tenant_id, user_id, customer_id=customer_id)
        run_ids.append(first_run["run_id"])

        with SessionLocal() as db:
            memory_row = db.execute(
                text(
                    """
                    SELECT memory_id, customer_id, summary_text, summary_json, source_run_id
                    FROM customer_memory
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().first()
            assert memory_row is not None
            memory_json = _loads_json(memory_row["summary_json"])
            assert memory_row["source_run_id"] == first_run["run_id"]
            assert memory_json["risk_state"]["latest_risk_level"] in {"medium", "high"}
            assert memory_json["approval_state"]["total_count"] >= 1

            first_load_step = db.execute(
                text(
                    """
                    SELECT output_json
                    FROM agent_step
                    WHERE tenant_id = :tenant_id AND run_id = :run_id AND node_name = 'load_customer_memory'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "run_id": first_run["run_id"]},
            ).scalar_one()
            first_load_output = _loads_json(first_load_step)
            assert first_load_output["memory_hit_count"] == 0

            first_persist_step = db.execute(
                text(
                    """
                    SELECT output_json
                    FROM agent_step
                    WHERE tenant_id = :tenant_id AND run_id = :run_id AND node_name = 'persist_customer_memory'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "run_id": first_run["run_id"]},
            ).scalar_one()
            first_persist_output = _loads_json(first_persist_step)
            assert first_persist_output["memory_updated_count"] == 1

        second_run = run_risk_analysis_workflow(tenant_id, user_id, customer_id=customer_id)
        run_ids.append(second_run["run_id"])

        with SessionLocal() as db:
            second_load_step = db.execute(
                text(
                    """
                    SELECT output_json
                    FROM agent_step
                    WHERE tenant_id = :tenant_id AND run_id = :run_id AND node_name = 'load_customer_memory'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "run_id": second_run["run_id"]},
            ).scalar_one()
            second_load_output = _loads_json(second_load_step)
            assert second_load_output["memory_hit_count"] == 1

            run_output = db.execute(
                text(
                    """
                    SELECT output_json
                    FROM agent_run
                    WHERE tenant_id = :tenant_id AND run_id = :run_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "run_id": second_run["run_id"]},
            ).scalar_one()
            run_output_json = _loads_json(run_output)
            assert run_output_json["memory_summary"]["memory_hit_count"] == 1
            assert run_output_json["memory_summary"]["memory_updated_count"] == 1

            updated_memory_row = db.execute(
                text(
                    """
                    SELECT source_run_id, summary_json
                    FROM customer_memory
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().first()
            assert updated_memory_row is not None
            assert updated_memory_row["source_run_id"] == second_run["run_id"]
            updated_memory_json = _loads_json(updated_memory_row["summary_json"])
            assert updated_memory_json["agent_state"]["source_run_id"] == second_run["run_id"]
    finally:
        _cleanup_customer_memory_fixture(tenant_id, customer_id, deal_id, report_id, run_ids)
