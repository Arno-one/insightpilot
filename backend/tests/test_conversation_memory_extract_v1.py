import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import conversation_memory_service
from app.modules.agent import memory_service as agent_memory_service
from app.modules.memory import conversation_fact_service


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _DummyQueue:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def enqueue(self, job_name: str, *args, **kwargs):
        self.calls.append((job_name, args, kwargs))

        class _Job:
            id = "rq_mem_extract_demo"

        return _Job()


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
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS conversation_memory_extract_job (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  extract_job_id VARCHAR(64) NOT NULL,
                  customer_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  source_type VARCHAR(30) NOT NULL DEFAULT 'risk_chat',
                  session_key VARCHAR(191) NOT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'queued',
                  trigger_message_count INT NOT NULL DEFAULT 0,
                  trigger_batch_json JSON NULL,
                  recent_window_json JSON NULL,
                  history_summary TEXT NULL,
                  queued_job_id VARCHAR(64) NULL,
                  extracted_facts_json JSON NULL,
                  error_message TEXT NULL,
                  started_at DATETIME NULL,
                  finished_at DATETIME NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_extract_job_id (extract_job_id),
                  KEY idx_tenant_customer_status (tenant_id, customer_id, status),
                  KEY idx_tenant_user_created (tenant_id, user_id, created_at),
                  KEY idx_tenant_session_created (tenant_id, session_key, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _cleanup_extract_fixture(tenant_id: str, customer_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM conversation_memory_extract_job WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_memory_atomic WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_append_conversation_messages_enqueues_long_term_fact_extraction(monkeypatch):
    tenant_id = f"tenant_extract_enqueue_{uuid4().hex[:8]}"
    user_id = f"user_extract_enqueue_{uuid4().hex[:8]}"
    customer_id = f"cust_extract_enqueue_{uuid4().hex[:8]}"
    fake_redis = _FakeRedis()
    dummy_queue = _DummyQueue()
    _ensure_customer_memory_atomic_table_exists()
    _cleanup_extract_fixture(tenant_id, customer_id)
    monkeypatch.setattr(conversation_fact_service, "get_default_queue", lambda: dummy_queue)

    try:
        memory, compacted = conversation_memory_service.append_conversation_messages(
            tenant_id,
            user_id,
            customer_id,
            messages=[
                {"role": "user", "content": "客户明确表示预算先控制在10万内。"},
                {"role": "assistant", "content": "建议先补ROI材料。"},
            ],
            redis_client=fake_redis,
        )

        with SessionLocal() as db:
            job = db.execute(
                text(
                    """
                    SELECT extract_job_id, status, trigger_message_count, queued_job_id
                    FROM conversation_memory_extract_job
                    WHERE tenant_id = :tenant_id
                      AND customer_id = :customer_id
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().first()

        assert compacted is False
        assert memory["recent_messages"]
        assert dummy_queue.calls[0][0] == "app.workers.memory_jobs.extract_customer_long_term_facts"
        assert dummy_queue.calls[0][1][0] == tenant_id
        assert dummy_queue.calls[0][1][2] == job["extract_job_id"]
        assert job["status"] == "queued"
        assert job["trigger_message_count"] == 2
        assert job["queued_job_id"] == "rq_mem_extract_demo"
    finally:
        _cleanup_extract_fixture(tenant_id, customer_id)


def test_conversation_fact_worker_persists_safe_atomic_facts_and_survives_summary_rebuild():
    tenant_id = f"tenant_extract_worker_{uuid4().hex[:8]}"
    user_id = f"user_extract_worker_{uuid4().hex[:8]}"
    customer_id = f"cust_extract_worker_{uuid4().hex[:8]}"
    now = datetime.now()
    _ensure_customer_memory_atomic_table_exists()
    _cleanup_extract_fixture(tenant_id, customer_id)

    try:
        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO conversation_memory_extract_job (
                      tenant_id, extract_job_id, customer_id, user_id, source_type, session_key, status,
                      trigger_message_count, trigger_batch_json, recent_window_json, history_summary
                    )
                    VALUES (
                      :tenant_id, 'memxjob_worker_1', :customer_id, :user_id, 'risk_chat', :session_key, 'queued',
                      3, :trigger_batch_json, :recent_window_json, ''
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "session_key": f"risk_chat:{tenant_id}:{user_id}:{customer_id}",
                    "trigger_batch_json": json.dumps(
                        [
                            {"role": "user", "content": "客户明确表示预算先控制在10万内。", "created_at": now.isoformat()},
                            {"role": "user", "content": "客户更偏好微信沟通。", "created_at": now.isoformat()},
                            {"role": "assistant", "content": "建议下周再跟进。", "created_at": now.isoformat()},
                        ],
                        ensure_ascii=False,
                    ),
                    "recent_window_json": json.dumps(
                        [
                            {"role": "user", "content": "这个客户是不是很犹豫？", "created_at": now.isoformat()},
                        ],
                        ensure_ascii=False,
                    ),
                },
            )
            db.commit()

        result = conversation_fact_service.run_conversation_long_term_fact_extraction_job(
            tenant_id,
            user_id,
            "memxjob_worker_1",
        )

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    """
                    SELECT memory_type, title, content, source_table
                    FROM customer_memory_atomic
                    WHERE tenant_id = :tenant_id
                      AND customer_id = :customer_id
                    ORDER BY order_index ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().all()
            job_status = db.execute(
                text(
                    """
                    SELECT status, extracted_facts_json
                    FROM conversation_memory_extract_job
                    WHERE tenant_id = :tenant_id
                      AND extract_job_id = 'memxjob_worker_1'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id},
            ).mappings().first()

            snapshot = {
                "customer_id": customer_id,
                "memory_scope": "customer",
                "summary_text": "客户进入机会阶段，需要持续跟进。",
                "summary_json": {"profile": {"intent_level": "high"}},
                "source_run_id": "run_extract_rebuild",
                "last_compiled_at": now,
                "atomic_memories": [
                    {
                        "memory_type": "world",
                        "title": "总结层事实",
                        "content": "客户当前处于机会阶段。",
                        "occurred_at": now,
                        "source_table": "customer_memory",
                        "source_id": customer_id,
                        "source_run_id": "run_extract_rebuild",
                        "evidence_refs": [],
                        "entity_keys": ["customer"],
                        "metadata_json": {},
                    }
                ],
            }
            agent_memory_service.upsert_customer_memory(db, tenant_id=tenant_id, memory_snapshot=snapshot)
            db.commit()
            source_counts = db.execute(
                text(
                    """
                    SELECT source_table, COUNT(*) AS count
                    FROM customer_memory_atomic
                    WHERE tenant_id = :tenant_id
                      AND customer_id = :customer_id
                    GROUP BY source_table
                    """
                ),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).mappings().all()

        assert result["fact_count"] == 2
        assert result["inserted_count"] == 2
        assert result["updated_count"] == 0
        assert job_status["status"] == "success"
        assert len(json.loads(job_status["extracted_facts_json"])) == 2
        assert len(rows) == 2
        assert all(row["source_table"] == conversation_fact_service.CONVERSATION_FACT_SOURCE_TABLE for row in rows)
        assert any("预算先控制在10万内" in row["content"] for row in rows)
        assert any("微信沟通" in row["content"] for row in rows)
        counts_by_source = {row["source_table"]: row["count"] for row in source_counts}
        assert counts_by_source[conversation_fact_service.CONVERSATION_FACT_SOURCE_TABLE] == 2
        assert counts_by_source["customer_memory"] == 1
    finally:
        _cleanup_extract_fixture(tenant_id, customer_id)
