import json
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.agent import conversation_memory_service
from app.modules.llm import client as llm_client


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


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


def _build_headers(
    client: TestClient,
    *,
    username: str = "manager",
    password: str = "Manager@123456",
) -> tuple[dict[str, str], str, str]:
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    login_body = login.json()["data"]
    return (
        {"Authorization": f"Bearer {login_body['token']}"},
        login_body["user"]["tenant_id"],
        login_body["user"]["user_id"],
    )


def _create_risk_chat_fixture(tenant_id: str, user_id: str) -> tuple[str, str]:
    customer_id = f"cust_chat_{uuid4().hex[:10]}"
    risk_snapshot_id = f"risk_chat_{uuid4().hex[:10]}"
    now = datetime.now()
    summary_json = {
        "profile": {
            "customer_id": customer_id,
            "customer_name": "对话记忆专项测试客户",
            "lifecycle_stage": "opportunity",
            "intent_level": "high",
            "last_sentiment": "negative",
        },
        "risk_state": {
            "latest_risk_level": "high",
            "latest_risk_score": 82,
            "latest_reason": "客户两周未推进且竞品介入明显。",
            "latest_suggestion": "建议主管介入并核对真实采购节奏。",
        },
        "approval_state": {
            "pending_count": 1,
        },
        "task_state": {
            "active_count": 0,
        },
        "follow_up_state": {
            "count": 2,
            "latest_follow_up_at": now.isoformat(),
        },
    }

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
                "customer_name": "对话记忆专项测试客户",
                "owner_user_id": user_id,
                "last_follow_up_at": now,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO customer_risk_snapshot (
                  tenant_id, risk_snapshot_id, customer_id, owner_user_id, risk_score, risk_level,
                  rule_hits_json, evidence_json, llm_reason, llm_suggestion, suggested_task_json,
                  status, generated_by_run_id
                )
                VALUES (
                  :tenant_id, :risk_snapshot_id, :customer_id, :owner_user_id, 82, 'high',
                  '[]', '{}', :llm_reason, :llm_suggestion, '{}', 'pending_review', NULL
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "risk_snapshot_id": risk_snapshot_id,
                "customer_id": customer_id,
                "owner_user_id": user_id,
                "llm_reason": "客户两周未推进且竞品介入明显。",
                "llm_suggestion": "建议主管介入并核对真实采购节奏。",
            },
        )
        db.execute(
            text(
                """
                INSERT INTO customer_memory (
                  tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
                )
                VALUES (
                  :tenant_id, :memory_id, :customer_id, 'customer', :summary_text, :summary_json, NULL, :last_compiled_at
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "memory_id": f"memo_chat_{uuid4().hex[:10]}",
                "customer_id": customer_id,
                "summary_text": "该客户近期推进放缓，存在竞品介入，建议主管介入核对采购节奏。",
                "summary_json": json.dumps(summary_json, ensure_ascii=False),
                "last_compiled_at": now,
            },
        )
        db.commit()

    return customer_id, risk_snapshot_id


def _cleanup_risk_chat_fixture(tenant_id: str, customer_id: str, risk_snapshot_id: str):
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM customer_memory WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.execute(
            text("DELETE FROM customer_risk_snapshot WHERE tenant_id = :tenant_id AND risk_snapshot_id = :risk_snapshot_id"),
            {"tenant_id": tenant_id, "risk_snapshot_id": risk_snapshot_id},
        )
        db.execute(
            text("DELETE FROM crm_customer WHERE tenant_id = :tenant_id AND customer_id = :customer_id"),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        )
        db.commit()


def test_load_conversation_memory_returns_empty_session_when_first_seen():
    fake_redis = _FakeRedis()

    memory = conversation_memory_service.load_conversation_memory(
        "tenant_demo",
        "user_demo",
        "customer_demo",
        redis_client=fake_redis,
    )

    assert memory["session_key"] == "risk_chat:tenant_demo:user_demo:customer_demo"
    assert memory["recent_messages"] == []
    assert memory["history_summary"] == ""
    assert memory["memory_window"]["recent_rounds"] == 5


def test_append_conversation_messages_keeps_recent_five_rounds_and_compacts_older_history():
    fake_redis = _FakeRedis()

    compacted = False
    for index in range(6):
        memory, compacted = conversation_memory_service.append_conversation_messages(
            "tenant_demo",
            "user_demo",
            "customer_demo",
            messages=[
                {"role": "user", "content": f"第{index + 1}轮用户问题"},
                {"role": "assistant", "content": f"第{index + 1}轮助手回复"},
            ],
            redis_client=fake_redis,
        )

    assert compacted is True
    assert len(memory["recent_messages"]) == 10
    assert memory["recent_messages"][0]["content"] == "第2轮用户问题"
    assert "第1轮用户问题" in memory["history_summary"]
    assert "第1轮助手回复" in memory["history_summary"]


def test_conversation_memory_is_isolated_by_user_and_customer():
    fake_redis = _FakeRedis()

    conversation_memory_service.append_conversation_messages(
        "tenant_demo",
        "user_a",
        "customer_demo",
        messages=[{"role": "user", "content": "用户A消息"}, {"role": "assistant", "content": "A回复"}],
        redis_client=fake_redis,
    )
    conversation_memory_service.append_conversation_messages(
        "tenant_demo",
        "user_b",
        "customer_demo",
        messages=[{"role": "user", "content": "用户B消息"}, {"role": "assistant", "content": "B回复"}],
        redis_client=fake_redis,
    )

    memory_a = conversation_memory_service.load_conversation_memory(
        "tenant_demo",
        "user_a",
        "customer_demo",
        redis_client=fake_redis,
    )
    memory_b = conversation_memory_service.load_conversation_memory(
        "tenant_demo",
        "user_b",
        "customer_demo",
        redis_client=fake_redis,
    )

    assert memory_a["recent_messages"][0]["content"] == "用户A消息"
    assert memory_b["recent_messages"][0]["content"] == "用户B消息"


def test_conversation_session_index_keeps_recent_title_and_preview():
    fake_redis = _FakeRedis()
    memory, _ = conversation_memory_service.append_conversation_messages(
        "tenant_demo",
        "user_demo",
        "customer_demo",
        messages=[
            {"role": "user", "content": "这个客户现在应该怎么回访？"},
            {"role": "assistant", "content": "建议先确认真实采购时间。"},
        ],
        redis_client=fake_redis,
    )

    items = conversation_memory_service.upsert_conversation_session_index(
        "tenant_demo",
        "user_demo",
        customer_id="customer_demo",
        customer_name="演示客户",
        session_key=memory["session_key"],
        recent_messages=memory["recent_messages"],
        updated_at=memory["updated_at"],
        latest_risk_level="high",
        redis_client=fake_redis,
    )

    assert len(items) == 1
    assert items[0]["title"] == "这个客户现在应该怎么"
    assert "Risk Agent" in items[0]["preview"]
    assert items[0]["latest_risk_level"] == "high"


def test_risk_chat_api_persists_messages_and_supports_clear(monkeypatch):
    client = TestClient(app)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(conversation_memory_service, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")
    _ensure_customer_memory_table_exists()
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_fixture(tenant_id, user_id)

    try:
        session_response = client.get(f"/api/agent/risk-chat/customers/{customer_id}/session", headers=headers)
        assert session_response.status_code == 200
        session_data = session_response.json()["data"]
        assert session_data["recent_messages"] == []
        assert "竞品介入" in session_data["customer_memory_summary"]

        message_response = client.post(
            f"/api/agent/risk-chat/customers/{customer_id}/message",
            headers=headers,
            json={"message": "这个客户现在应该怎么回访？"},
        )
        assert message_response.status_code == 200
        message_data = message_response.json()["data"]
        assert "建议下一次沟通先确认真实采购时间" in message_data["reply"]
        assert len(message_data["recent_messages"]) == 2
        assert message_data["recent_messages"][0]["role"] == "user"
        assert message_data["recent_messages"][1]["role"] == "assistant"
        assert len(message_data["session_history"]) == 1
        assert message_data["session_history"][0]["customer_id"] == customer_id

        clear_response = client.delete(f"/api/agent/risk-chat/customers/{customer_id}/session", headers=headers)
        assert clear_response.status_code == 200
        assert clear_response.json()["data"]["session_history"] == []

        refreshed_session = client.get(f"/api/agent/risk-chat/customers/{customer_id}/session", headers=headers)
        assert refreshed_session.status_code == 200
        assert refreshed_session.json()["data"]["recent_messages"] == []
    finally:
        _cleanup_risk_chat_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_risk_chat_api_compacts_history_after_more_than_five_rounds(monkeypatch):
    client = TestClient(app)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(conversation_memory_service, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")
    _ensure_customer_memory_table_exists()
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_fixture(tenant_id, user_id)

    try:
        compacted = False
        for index in range(6):
            response = client.post(
                f"/api/agent/risk-chat/customers/{customer_id}/message",
                headers=headers,
                json={"message": f"第{index + 1}轮怎么回访这个客户？"},
            )
            assert response.status_code == 200
            compacted = response.json()["data"]["compacted"]

        session_response = client.get(f"/api/agent/risk-chat/customers/{customer_id}/session", headers=headers)
        assert session_response.status_code == 200
        session_data = session_response.json()["data"]

        assert compacted is True
        assert len(session_data["recent_messages"]) == 10
        assert session_data["recent_messages"][0]["content"] == "第2轮怎么回访这个客户？"
        assert "第1轮怎么回访这个客户？" in session_data["history_summary"]
    finally:
        _cleanup_risk_chat_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_risk_chat_history_api_lists_recent_sessions_and_salesperson_can_access(monkeypatch):
    client = TestClient(app)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(conversation_memory_service, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")
    _ensure_customer_memory_table_exists()
    headers, tenant_id, user_id = _build_headers(client, username="sales01", password="Sales@123456")
    customer_id, risk_snapshot_id = _create_risk_chat_fixture(tenant_id, user_id)

    try:
        message_response = client.post(
            f"/api/agent/risk-chat/customers/{customer_id}/message",
            headers=headers,
            json={"message": "帮我判断这个客户今天要不要继续跟进"},
        )
        assert message_response.status_code == 200

        history_response = client.get("/api/agent/risk-chat/sessions", headers=headers)
        assert history_response.status_code == 200
        history_items = history_response.json()["data"]

        assert len(history_items) == 1
        assert history_items[0]["customer_id"] == customer_id
        assert len(history_items[0]["title"]) <= 10
        assert history_items[0]["customer_name"] == "对话记忆专项测试客户"
    finally:
        _cleanup_risk_chat_fixture(tenant_id, customer_id, risk_snapshot_id)
