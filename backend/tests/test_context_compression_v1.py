import json
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.memory import service as memory_service


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


def _cleanup_context_packet_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM customer_memory_atomic WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
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


def test_customer_context_packet_compresses_memory_under_budget():
    tenant_id = f"tenant_context_packet_{uuid4().hex[:8]}"
    user_id = f"user_context_packet_{uuid4().hex[:8]}"
    customer_id = f"cust_context_packet_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    now = datetime.now()
    _ensure_customer_memory_atomic_table_exists()
    _cleanup_context_packet_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO crm_customer (
                      tenant_id, customer_id, customer_name, owner_user_id, industry, region,
                      lifecycle_stage, intent_level, customer_level, competitor_involved,
                      next_follow_up_at, last_follow_up_at, last_sentiment
                    )
                    VALUES (
                      :tenant_id, :customer_id, '上下文压缩测试客户', :user_id, '医疗', '华北',
                      'opportunity', 'high', 'A', 1,
                      :next_follow_up_at, :last_follow_up_at, 'negative'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "next_follow_up_at": now + timedelta(days=1),
                    "last_follow_up_at": now - timedelta(days=2),
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_risk_snapshot (
                      tenant_id, risk_snapshot_id, customer_id, owner_user_id, risk_score,
                      risk_level, rule_hits_json, evidence_json, llm_reason, llm_suggestion,
                      suggested_task_json, status, created_at
                    )
                    VALUES (
                      :tenant_id, 'risk_context_packet', :customer_id, :user_id, 91,
                      'high', '[]', '{}', '客户长期未确认预算且竞品介入',
                      '建议主管介入并补充 ROI 证明', '{}', 'pending_review', :created_at
                    )
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id, "user_id": user_id, "created_at": now},
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory (
                      tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                    )
                    VALUES (
                      :tenant_id, 'memory_context_packet', :customer_id, 'customer',
                      :summary_text, :summary_json, 'run_context_packet', :last_compiled_at
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "summary_text": "客户需要 ROI 证明、竞品对比、主管背书。" * 80,
                    "summary_json": json.dumps(
                        {
                            "profile": {"intent_level": "high", "lifecycle_stage": "opportunity"},
                            "profile_tags": {"risk_tag": "风险:high/91", "competition_tag": "竞品:已介入"},
                        },
                        ensure_ascii=False,
                    ),
                    "last_compiled_at": now,
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO customer_memory_atomic (
                      tenant_id, atomic_memory_id, memory_id, customer_id, memory_scope, memory_type,
                      order_index, title, content, confidence, occurred_at, source_table, source_id,
                      source_run_id, evidence_refs_json, entity_keys_json, metadata_json
                    )
                    VALUES
                      (:tenant_id, 'atom_context_world', 'memory_context_packet', :customer_id, 'customer', 'world',
                       1, '客户画像事实', '客户尚未确认预算，且竞品已介入。', NULL, :occurred_at, 'crm_customer', :customer_id,
                       'run_context_packet', '[]', '[]', '{}'),
                      (:tenant_id, 'atom_context_opinion', 'memory_context_packet', :customer_id, 'customer', 'opinion',
                       2, '风险判断', '系统判断需要主管介入并补充 ROI 证明。', 0.9100, :occurred_at, 'customer_risk_snapshot', 'risk_context_packet',
                       'run_context_packet', '[]', '[]', '{}')
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "occurred_at": now,
                },
            )
            db.commit()

            packet = memory_service.build_customer_context_packet(
                db,
                current_user,
                customer_id=customer_id,
                max_chars=700,
            )

        assert packet["source_type"] == "runtime_context_packet"
        assert packet["budget"]["max_chars"] == 700
        assert packet["budget"]["used_chars"] <= 700
        assert packet["budget"]["overflow"] is True
        assert packet["raw_refs"]["customer_memory_id"] == "memory_context_packet"
        assert packet["raw_refs"]["atomic_memory_count"] == 2
        assert packet["sections"][0]["section_type"] == "customer_profile"
        assert "上下文压缩测试客户" in packet["compressed_context"]
        assert "当前状态" in packet["compressed_context"]
        assert any(section["section_type"] == "compiled_memory" for section in packet["sections"])
    finally:
        _cleanup_context_packet_fixture(tenant_id, customer_id)
