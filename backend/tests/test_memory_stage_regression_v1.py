import json
from datetime import datetime

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.memory import service as memory_service


class _EmptyRedis:
    def get(self, _key):
        return None


def _ensure_memory_stage_tables_exist():
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


def _cleanup_memory_stage_fixture(tenant_id: str):
    with SessionLocal() as db:
        for table in ["memory_governance_state", "memory_update_trace", "customer_memory"]:
            db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_memory_stage_overview_rolls_up_stage_capabilities():
    _ensure_memory_stage_tables_exist()
    tenant_id = "tenant_memory_stage_v1"
    user_id = "user_memory_stage_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    now = datetime.now()
    _cleanup_memory_stage_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory (
                      tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                    )
                    VALUES (
                      :tenant_id, 'memory_stage_overview', 'cust_stage_overview', 'customer',
                      'Memory 阶段回归测试摘要。', :summary_json, 'run_stage_overview', :last_compiled_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "summary_json": json.dumps({"profile_tags": {"risk_tag": "风险:medium/66"}}, ensure_ascii=False),
                    "last_compiled_at": now,
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO memory_update_trace (
                      tenant_id, trace_id, memory_id, customer_id, memory_scope, update_type,
                      source_type, source_run_id, changed_fields_json, summary_preview, profile_tags_json, metadata_json
                    )
                    VALUES (
                      :tenant_id, 'trace_stage_overview', 'memory_stage_overview', 'cust_stage_overview', 'customer',
                      'create', 'agent_run', 'run_stage_overview', :changed_fields_json,
                      'Memory 阶段回归测试摘要。', :profile_tags_json, '{}'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "changed_fields_json": json.dumps(["summary_text"], ensure_ascii=False),
                    "profile_tags_json": json.dumps({"risk_tag": "风险:medium/66"}, ensure_ascii=False),
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO memory_governance_state (
                      tenant_id, governance_id, memory_id, customer_id, memory_scope,
                      governance_status, refresh_status, reason
                    )
                    VALUES (
                      :tenant_id, 'gov_stage_overview', 'memory_stage_overview', 'cust_stage_overview', 'customer',
                      'disabled', 'requested', '阶段回归测试'
                    )
                    """
                ),
                {"tenant_id": tenant_id},
            )
            db.commit()

            overview = memory_service.summarize_memory_system(db, current_user, redis_client=_EmptyRedis())

        assert overview["source_type"] == "memory_system_overview"
        assert overview["stage_status"] == "memory_stage_v1_ready"
        assert overview["customer_memory"]["total_count"] == 1
        assert overview["update_trace"]["total_count"] == 1
        assert overview["update_trace"]["recent_traces"][0]["trace_id"] == "trace_stage_overview"
        assert overview["governance"]["by_governance_status"]["disabled"] == 1
        assert overview["governance"]["by_refresh_status"]["requested"] == 1
        assert "context_compression" in overview["capabilities"]
        assert "memory_governance" in overview["capabilities"]
    finally:
        _cleanup_memory_stage_fixture(tenant_id)
