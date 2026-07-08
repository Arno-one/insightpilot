import json
from datetime import datetime
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


def _cleanup_search_fixture(tenant_id: str, customer_id: str):
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
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def _seed_search_fixture(tenant_id: str, user_id: str, customer_id: str):
    now = datetime.now()
    with SessionLocal() as db:
        db.execute(
            text(
                """
                INSERT INTO crm_customer (
                  tenant_id, customer_id, customer_name, owner_user_id, lifecycle_stage, intent_level
                )
                VALUES (
                  :tenant_id, :customer_id, '长期检索测试客户', :user_id, 'opportunity', 'high'
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
                  :tenant_id, 'memory_search_demo', :customer_id, 'customer',
                  :summary_text, :summary_json, 'run_search_demo', :last_compiled_at
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "customer_id": customer_id,
                "summary_text": "客户长期关注 ROI 证明、竞品对比和预算控制。",
                "summary_json": json.dumps({"profile": {"intent_level": "high"}}, ensure_ascii=False),
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
                  (:tenant_id, 'atom_search_world', 'memory_search_demo', :customer_id, 'customer', 'world',
                   1, '客户长期事实', '客户一直关注 ROI 证明和竞品对比，预算也比较谨慎。', NULL, :occurred_at, 'crm_customer', :customer_id,
                   'run_search_demo', '[]', '[\"roi\",\"竞品\",\"预算\"]', '{}'),
                  (:tenant_id, 'atom_search_opinion', 'memory_search_demo', :customer_id, 'customer', 'opinion',
                   2, '系统判断', '系统判断当前需要补充量化 ROI 证明，并由主管辅助推进。', 0.9100, :occurred_at, 'customer_risk_snapshot', 'risk_search_demo',
                   'run_search_demo', '[]', '[\"roi\",\"主管\"]', '{}'),
                  (:tenant_id, 'atom_search_experience', 'memory_search_demo', :customer_id, 'customer', 'experience',
                   3, '历史经验', '历史上发送 ROI 材料后，客户反馈会更积极。', NULL, :occurred_at, 'sales_task', 'task_search_demo',
                   'run_search_demo', '[]', '[\"roi\"]', '{}'),
                  (:tenant_id, 'atom_search_observation', 'memory_search_demo', :customer_id, 'customer', 'observation',
                   4, '近期观察', '客户上次明确提到预算先控制在 10 万内。', NULL, :occurred_at, 'crm_follow_up_record', 'follow_search_demo',
                   'run_search_demo', '[]', '[\"预算\"]', '{}')
                """
            ),
            {"tenant_id": tenant_id, "customer_id": customer_id, "occurred_at": now},
        )
        db.commit()


def test_customer_long_term_search_hits_query_relevant_atomic_memories():
    tenant_id = f"tenant_long_search_{uuid4().hex[:8]}"
    user_id = f"user_long_search_{uuid4().hex[:8]}"
    customer_id = f"cust_long_search_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    _ensure_customer_memory_atomic_table_exists()
    _cleanup_search_fixture(tenant_id, customer_id)

    try:
        _seed_search_fixture(tenant_id, user_id, customer_id)
        with SessionLocal() as db:
            result = memory_service.search_customer_long_term_memory(
                db,
                current_user,
                customer_id=customer_id,
                question="这个客户为什么一直关注ROI和竞品对比？",
                limit=3,
            )

        assert result["source_type"] == "customer_long_term_search"
        assert result["question"] == "这个客户为什么一直关注ROI和竞品对比？"
        assert result["hits"]
        assert "roi" in result["query_terms"]
        assert result["hits"][0]["memory_type"] in {"world", "opinion"}
        assert any("ROI" in item["content"] or "roi" in item["content"].lower() for item in result["hits"])
        assert result["grouped_hits"]["world"][0]["matched_terms"]
        assert result["recall_summary"]["matched_count"] == len(result["hits"])
        assert "ROI" in result["suggested_context"]["compressed_context"]
        assert result["summary_memory"]["included"] is True
    finally:
        _cleanup_search_fixture(tenant_id, customer_id)


def test_customer_long_term_search_supports_memory_type_filters():
    tenant_id = f"tenant_long_search_filter_{uuid4().hex[:8]}"
    user_id = f"user_long_search_filter_{uuid4().hex[:8]}"
    customer_id = f"cust_long_search_filter_{uuid4().hex[:8]}"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    _ensure_customer_memory_atomic_table_exists()
    _cleanup_search_fixture(tenant_id, customer_id)

    try:
        _seed_search_fixture(tenant_id, user_id, customer_id)
        with SessionLocal() as db:
            result = memory_service.search_customer_long_term_memory(
                db,
                current_user,
                customer_id=customer_id,
                question="现在是不是需要主管介入并补ROI证明？",
                limit=5,
                memory_types=["opinion"],
            )

        assert result["memory_types"] == ["opinion"]
        assert result["hits"]
        assert all(item["memory_type"] == "opinion" for item in result["hits"])
        assert result["hits"][0]["confidence"] == 0.91
        assert result["recall_summary"]["applied_memory_types"] == ["opinion"]
    finally:
        _cleanup_search_fixture(tenant_id, customer_id)
