import json
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

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


def _ensure_agent_chat_tables_exist():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_session (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  session_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  agent_scope VARCHAR(50) NOT NULL DEFAULT 'general',
                  intent VARCHAR(50) NOT NULL DEFAULT 'unknown',
                  title VARCHAR(120) NOT NULL DEFAULT '新对话',
                  status VARCHAR(30) NOT NULL DEFAULT 'active',
                  related_customer_id VARCHAR(64) NULL,
                  memory_key VARCHAR(180) NULL,
                  context_json JSON NULL,
                  last_message_role VARCHAR(30) NULL,
                  last_message_preview VARCHAR(255) NULL,
                  message_count INT NOT NULL DEFAULT 0,
                  last_message_at DATETIME NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_session_id (session_id),
                  KEY idx_tenant_user_updated (tenant_id, user_id, updated_at),
                  KEY idx_tenant_scope_intent (tenant_id, agent_scope, intent),
                  KEY idx_tenant_customer_updated (tenant_id, related_customer_id, updated_at),
                  KEY idx_tenant_status_updated (tenant_id, status, updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_chat_message (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  message_id VARCHAR(64) NOT NULL,
                  session_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  role VARCHAR(30) NOT NULL,
                  content TEXT NOT NULL,
                  intent VARCHAR(50) NULL,
                  tool_name VARCHAR(120) NULL,
                  run_id VARCHAR(64) NULL,
                  trace_id VARCHAR(64) NULL,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_message_id (message_id),
                  KEY idx_tenant_session_created (tenant_id, session_id, created_at),
                  KEY idx_tenant_user_created (tenant_id, user_id, created_at),
                  KEY idx_tenant_run (tenant_id, run_id),
                  KEY idx_tenant_trace (tenant_id, trace_id)
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


def _cleanup_agent_chat_sessions(tenant_id: str, session_ids: list[str]):
    if not session_ids:
        return
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM agent_chat_message WHERE tenant_id = :tenant_id AND session_id IN :session_ids").bindparams(
                bindparam("session_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "session_ids": session_ids},
        )
        db.execute(
            text("DELETE FROM agent_chat_session WHERE tenant_id = :tenant_id AND session_id IN :session_ids").bindparams(
                bindparam("session_ids", expanding=True)
            ),
            {"tenant_id": tenant_id, "session_ids": session_ids},
        )
        db.commit()


def _create_risk_chat_customer_fixture(tenant_id: str, user_id: str) -> tuple[str, str]:
    customer_id = f"cust_unified_{uuid4().hex[:10]}"
    risk_snapshot_id = f"risk_unified_{uuid4().hex[:10]}"
    now = datetime.now()
    summary_json = {
        "risk_state": {
            "latest_risk_level": "high",
            "latest_risk_score": 86,
            "latest_reason": "客户连续两周未推进且竞品介入明显。",
            "latest_suggestion": "建议主管介入并核对真实采购节奏。",
        },
        "approval_state": {"pending_count": 0},
        "task_state": {"active_count": 0},
        "follow_up_state": {"latest_follow_up_at": now.isoformat()},
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
                "customer_name": "统一入口风险运行时测试客户",
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
                  :tenant_id, :risk_snapshot_id, :customer_id, :owner_user_id, 86, 'high',
                  '[]', '{}', :llm_reason, :llm_suggestion, '{}', 'pending_review', NULL
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "risk_snapshot_id": risk_snapshot_id,
                "customer_id": customer_id,
                "owner_user_id": user_id,
                "llm_reason": "客户连续两周未推进且竞品介入明显。",
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
                "memory_id": f"memo_unified_{uuid4().hex[:10]}",
                "customer_id": customer_id,
                "summary_text": "该客户推进放缓且竞品介入，适合由主管介入核对采购节奏。",
                "summary_json": json.dumps(summary_json, ensure_ascii=False),
                "last_compiled_at": now,
            },
        )
        db.commit()

    return customer_id, risk_snapshot_id


def _cleanup_risk_chat_customer_fixture(tenant_id: str, customer_id: str, risk_snapshot_id: str):
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


def test_unified_agent_chat_api_creates_session_appends_message_and_closes():
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "general",
                "intent": "customer_query",
                "title": "统一对话入口专项测试",
                "context_json": {"source": "api_test"},
            },
        )
        assert create_response.status_code == 200
        created_session = create_response.json()["data"]
        session_ids.append(created_session["session_id"])
        assert created_session["message_count"] == 0
        assert created_session["context_json"]["source"] == "api_test"

        message_response = client.post(
            f"/api/agent/chat/sessions/{created_session['session_id']}/messages",
            headers=headers,
            json={
                "role": "user",
                "content": "帮我看看这个客户最近有什么风险",
                "intent": "risk_analysis",
                "metadata_json": {"from": "unified_api"},
            },
        )
        assert message_response.status_code == 200
        message_data = message_response.json()["data"]
        assert message_data["message"]["role"] == "user"
        assert message_data["message"]["metadata_json"]["from"] == "unified_api"
        assert message_data["intent_route"]["intent"] == "risk_analysis"
        assert message_data["message"]["metadata_json"]["intent_route"]["intent"] == "risk_analysis"
        assert message_data["session"]["message_count"] == 1
        assert message_data["session"]["last_message_role"] == "user"

        detail_response = client.get(f"/api/agent/chat/sessions/{created_session['session_id']}", headers=headers)
        assert detail_response.status_code == 200
        detail_data = detail_response.json()["data"]
        assert detail_data["session"]["session_id"] == created_session["session_id"]
        assert len(detail_data["messages"]) == 1
        assert detail_data["messages"][0]["content"] == "帮我看看这个客户最近有什么风险"

        list_response = client.get("/api/agent/chat/sessions?agent_scope=general", headers=headers)
        assert list_response.status_code == 200
        listed_ids = [item["session_id"] for item in list_response.json()["data"]]
        assert created_session["session_id"] in listed_ids

        close_response = client.post(f"/api/agent/chat/sessions/{created_session['session_id']}/close", headers=headers)
        assert close_response.status_code == 200
        assert close_response.json()["data"]["status"] == "closed"

        active_response = client.get("/api/agent/chat/sessions?agent_scope=general", headers=headers)
        assert active_response.status_code == 200
        active_ids = [item["session_id"] for item in active_response.json()["data"]]
        assert created_session["session_id"] not in active_ids
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)


def test_unified_agent_chat_api_runs_risk_agent_when_session_has_related_customer(monkeypatch):
    _ensure_agent_chat_tables_exist()
    _ensure_customer_memory_table_exists()
    client = TestClient(app)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(conversation_memory_service, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "risk",
                "intent": "unknown",
                "title": "统一风险运行时",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "这个客户为什么风险这么高？"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "risk_agent"
        assert "风险" in data["runtime"]["reply"]
        assert data["assistant_message"]["role"] == "assistant"
        assert data["assistant_message"]["metadata_json"]["runtime_handler"] == "risk_agent"
        assert data["session"]["message_count"] == 2
        assert data["session"]["last_message_role"] == "assistant"
        assert len(data["runtime"]["risk_chat"]["recent_messages"]) == 2

        detail_response = client.get(f"/api/agent/chat/sessions/{session_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]
        assert [item["role"] for item in detail["messages"]] == ["user", "assistant"]

        risk_session_response = client.get(f"/api/agent/risk-chat/customers/{customer_id}/session", headers=headers)
        assert risk_session_response.status_code == 200
        assert len(risk_session_response.json()["data"]["recent_messages"]) == 2
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_unified_agent_chat_api_rejects_assistant_message_from_direct_entry():
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={"agent_scope": "general", "intent": "unknown", "title": "角色校验测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "assistant", "content": "我是假冒助手回复"},
        )
        assert message_response.status_code == 400
        assert "仅允许直接写入用户消息" in message_response.json()["detail"]
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)


def test_unified_agent_chat_intent_route_api_returns_deterministic_result():
    client = TestClient(app)
    headers, _, _ = _build_headers(client)

    response = client.post(
        "/api/agent/chat/intent",
        headers=headers,
        json={"question": "统计一下本月客户总数和高风险客户数量"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["intent"] == "data_query"
    assert data["confidence"] >= 0.6
    assert "统计" in data["matched_keywords"]


def test_unified_agent_chat_api_isolated_by_current_user():
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    manager_headers, tenant_id, _ = _build_headers(client)
    sales_headers, _, _ = _build_headers(client, username="sales01", password="Sales@123456")
    session_ids: list[str] = []

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=manager_headers,
            json={"agent_scope": "general", "intent": "customer_query", "title": "用户隔离测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        forbidden_detail = client.get(f"/api/agent/chat/sessions/{session_id}", headers=sales_headers)
        assert forbidden_detail.status_code == 404

        forbidden_message = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=sales_headers,
            json={"role": "user", "content": "我不应该能写入别人的会话"},
        )
        assert forbidden_message.status_code == 404
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
