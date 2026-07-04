import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.memory import service as memory_service


def _ensure_memory_governance_tables_exist():
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
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_governance_state (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  governance_id VARCHAR(64) NOT NULL,
                  memory_id VARCHAR(64) NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  memory_scope VARCHAR(30) NOT NULL DEFAULT 'customer',
                  governance_status VARCHAR(30) NOT NULL DEFAULT 'enabled',
                  refresh_status VARCHAR(30) NOT NULL DEFAULT 'idle',
                  reason VARCHAR(500) NULL,
                  disabled_at DATETIME NULL,
                  disabled_by_user_id VARCHAR(64) NULL,
                  refresh_requested_at DATETIME NULL,
                  refresh_requested_by_user_id VARCHAR(64) NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_governance_id (governance_id),
                  UNIQUE KEY uk_tenant_customer_scope (tenant_id, customer_id, memory_scope),
                  KEY idx_tenant_status (tenant_id, governance_status),
                  KEY idx_tenant_refresh_status (tenant_id, refresh_status),
                  KEY idx_tenant_memory (tenant_id, memory_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _cleanup_memory_governance_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM memory_governance_state WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
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


def test_customer_memory_governance_supports_disable_enable_and_refresh_request():
    _ensure_memory_governance_tables_exist()
    tenant_id = f"tenant_memgov_{uuid4().hex[:8]}"
    user_id = f"user_memgov_{uuid4().hex[:8]}"
    customer_id = f"cust_memgov_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    now = datetime.now()
    _cleanup_memory_governance_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO crm_customer (
                      tenant_id, customer_id, customer_name, owner_user_id,
                      lifecycle_stage, intent_level, customer_level, competitor_involved, last_sentiment
                    )
                    VALUES (
                      :tenant_id, :customer_id, '记忆治理测试客户', :user_id,
                      'opportunity', 'high', 'A', 0, 'neutral'
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id},
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory (
                      tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                    )
                    VALUES (
                      :tenant_id, 'memory_governance', :customer_id, 'customer',
                      '客户记忆治理测试摘要。', :summary_json, 'run_governance', :last_compiled_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "summary_json": json.dumps({"profile_tags": {"intent_tag": "意向:high"}}, ensure_ascii=False),
                    "last_compiled_at": now,
                },
            )
            db.commit()

            initial = memory_service.load_customer_memory_governance(db, current_user, customer_id=customer_id)
            disabled = memory_service.update_customer_memory_governance(
                db,
                current_user,
                customer_id=customer_id,
                action="disable",
                reason="客户要求暂不使用历史记忆",
            )
            enabled = memory_service.update_customer_memory_governance(
                db,
                current_user,
                customer_id=customer_id,
                action="enable",
                reason="客户已重新授权使用",
            )
            refresh_requested = memory_service.update_customer_memory_governance(
                db,
                current_user,
                customer_id=customer_id,
                action="request_refresh",
                reason="客户画像已过期",
            )

        assert initial["memory"]["memory_id"] == "memory_governance"
        assert initial["governance"]["governance_status"] == "enabled"
        assert disabled["governance"]["governance_status"] == "disabled"
        assert disabled["governance"]["disabled_by_user_id"] == user_id
        assert disabled["governance"]["reason"] == "客户要求暂不使用历史记忆"
        assert enabled["governance"]["governance_status"] == "enabled"
        assert enabled["governance"]["disabled_at"] is None
        assert refresh_requested["governance"]["refresh_status"] == "requested"
        assert refresh_requested["governance"]["refresh_requested_by_user_id"] == user_id
        assert refresh_requested["governance"]["reason"] == "客户画像已过期"
    finally:
        _cleanup_memory_governance_fixture(tenant_id, customer_id)
