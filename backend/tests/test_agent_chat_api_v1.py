from fastapi.testclient import TestClient
from sqlalchemy import bindparam, text

from app.core.database import SessionLocal
from app.main import app


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
