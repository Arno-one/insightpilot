import json
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import memory_service as agent_memory_service
from app.modules.memory import service as memory_service


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


def _ensure_memory_update_trace_table_exists():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_update_trace (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  trace_id VARCHAR(64) NOT NULL,
                  memory_id VARCHAR(64) NOT NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer',
                  update_type VARCHAR(30) NOT NULL,
                  source_type VARCHAR(50) NOT NULL,
                  source_run_id VARCHAR(64) NULL,
                  changed_fields_json JSON NULL,
                  summary_preview TEXT NULL,
                  profile_tags_json JSON NULL,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_trace_id (trace_id),
                  KEY idx_tenant_customer_created (tenant_id, customer_id, created_at),
                  KEY idx_tenant_memory_created (tenant_id, memory_id, created_at),
                  KEY idx_tenant_source_run (tenant_id, source_run_id),
                  KEY idx_tenant_update_type (tenant_id, update_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _ensure_customer_memory_atomic_table_exists():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS customer_memory_atomic (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  atomic_memory_id VARCHAR(64) NOT NULL,
                  memory_id VARCHAR(64) NOT NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer',
                  memory_type VARCHAR(30) NOT NULL,
                  order_index INT NOT NULL DEFAULT 0,
                  title VARCHAR(255) NULL,
                  content TEXT NOT NULL,
                  confidence DECIMAL(6,4) NULL,
                  occurred_at DATETIME NULL,
                  source_table VARCHAR(64) NOT NULL,
                  source_id VARCHAR(64) NULL,
                  source_run_id VARCHAR(64) NULL,
                  evidence_refs_json JSON NULL,
                  entity_keys_json JSON NULL,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_atomic_memory_id (atomic_memory_id),
                  KEY idx_tenant_customer_type_time (tenant_id, customer_id, memory_type, occurred_at),
                  KEY idx_tenant_memory_order (tenant_id, memory_id, order_index),
                  KEY idx_tenant_source_run (tenant_id, source_run_id),
                  KEY idx_tenant_source_table (tenant_id, source_table, source_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _cleanup_memory_update_trace_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM customer_memory_atomic WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM memory_update_trace WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_customer_memory_upsert_writes_queryable_update_trace():
    _ensure_customer_memory_table_exists()
    _ensure_memory_update_trace_table_exists()
    _ensure_customer_memory_atomic_table_exists()
    tenant_id = f"tenant_memtrace_{uuid4().hex[:8]}"
    user_id = f"user_memtrace_{uuid4().hex[:8]}"
    customer_id = f"cust_memtrace_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_memory_update_trace_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO crm_customer (
                      tenant_id, customer_id, customer_name, owner_user_id, lifecycle_stage,
                      intent_level, customer_level, competitor_involved, last_sentiment
                    )
                    VALUES (
                      :tenant_id, :customer_id, '记忆轨迹测试客户', :user_id, 'lead',
                      'medium', 'B', 0, 'neutral'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id},
            )
            first_snapshot = agent_memory_service.build_customer_memory_snapshot(
                db,
                tenant_id=tenant_id,
                customer_id=customer_id,
                source_run_id="run_memtrace_1",
                runtime_context={"review": {"summary": "首次生成客户记忆"}},
            )
            assert first_snapshot is not None
            first_memory = agent_memory_service.upsert_customer_memory(
                db,
                tenant_id=tenant_id,
                memory_snapshot=first_snapshot,
            )
            second_snapshot = agent_memory_service.build_customer_memory_snapshot(
                db,
                tenant_id=tenant_id,
                customer_id=customer_id,
                source_run_id="run_memtrace_2",
                runtime_context={"review": {"summary": "第二次刷新客户记忆"}},
            )
            assert second_snapshot is not None
            second_memory = agent_memory_service.upsert_customer_memory(
                db,
                tenant_id=tenant_id,
                memory_snapshot=second_snapshot,
            )
            db.commit()

            trace_rows = db.execute(
                text(
                    """
                    SELECT update_type, source_type, source_run_id, changed_fields_json, profile_tags_json
                    FROM memory_update_trace
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().all()
            queried_traces = memory_service.list_customer_memory_update_traces(
                db,
                current_user,
                customer_id=customer_id,
                limit=10,
            )
            atomic_rows = db.execute(
                text(
                    """
                    SELECT memory_type, confidence
                    FROM customer_memory_atomic
                    WHERE tenant_id = :tenant_id AND customer_id = :customer_id
                    ORDER BY order_index ASC
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().all()

        assert first_memory["update_trace"]["update_type"] == "create"
        assert second_memory["update_trace"]["update_type"] == "update"
        assert second_memory["atomic_refresh"]["total_count"] == len(atomic_rows)
        assert len(trace_rows) == 2
        assert trace_rows[0]["update_type"] == "create"
        assert trace_rows[1]["update_type"] == "update"
        assert trace_rows[1]["source_type"] == "agent_run"
        assert trace_rows[1]["source_run_id"] == "run_memtrace_2"
        assert "summary_json" in json.loads(trace_rows[1]["changed_fields_json"])
        assert json.loads(trace_rows[1]["profile_tags_json"])["intent_tag"] == "意向:medium"

        assert {row["memory_type"] for row in atomic_rows}.issuperset({"world", "opinion", "observation"})
        assert any(row["confidence"] is not None for row in atomic_rows if row["memory_type"] == "opinion")
        assert len(queried_traces) == 2
        assert queried_traces[0]["update_type"] == "update"
        assert queried_traces[0]["changed_fields"]
        assert queried_traces[0]["profile_tags"]["intent_tag"] == "意向:medium"
    finally:
        _cleanup_memory_update_trace_fixture(tenant_id, customer_id)
