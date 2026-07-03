from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import chat_session_service


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


def _cleanup_agent_chat_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM agent_chat_message WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM agent_chat_session WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_create_agent_chat_session_keeps_context_and_memory_key():
    _ensure_agent_chat_tables_exist()
    tenant_id = f"tenant_chat_{uuid4().hex[:8]}"
    user_id = f"user_chat_{uuid4().hex[:8]}"

    try:
        with SessionLocal() as db:
            session = chat_session_service.create_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_scope="risk",
                intent="risk_analysis",
                title="风险客户统一入口",
                related_customer_id="cust_demo",
                context_json={"source": "risk_chat", "version": "VNext-1"},
            )

            assert session["session_id"].startswith("chat_sess_")
            assert session["agent_scope"] == "risk"
            assert session["intent"] == "risk_analysis"
            assert session["title"] == "风险客户统一入口"
            assert session["related_customer_id"] == "cust_demo"
            assert session["memory_key"].startswith(f"agent_chat:{tenant_id}:{user_id}:")
            assert session["context_json"]["source"] == "risk_chat"
            assert session["message_count"] == 0
    finally:
        _cleanup_agent_chat_fixture(tenant_id)


def test_append_agent_chat_messages_updates_session_index_and_keeps_order():
    _ensure_agent_chat_tables_exist()
    tenant_id = f"tenant_chat_{uuid4().hex[:8]}"
    user_id = f"user_chat_{uuid4().hex[:8]}"

    try:
        with SessionLocal() as db:
            session = chat_session_service.create_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_scope="general",
                intent="unknown",
                title="新对话",
            )
            session_id = session["session_id"]

            messages = chat_session_service.append_chat_messages(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                messages=[
                    {"role": "user", "content": "帮我看一下这个客户风险为什么升高", "intent": "risk_analysis"},
                    {
                        "role": "assistant",
                        "content": "主要原因是长期未跟进、竞品介入和待审批动作积压。",
                        "intent": "risk_analysis",
                        "metadata_json": {"source": "fallback"},
                    },
                ],
            )

            refreshed_session = chat_session_service.get_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
            persisted_messages = chat_session_service.list_chat_messages(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )

            assert len(messages) == 2
            assert refreshed_session["message_count"] == 2
            assert refreshed_session["intent"] == "risk_analysis"
            assert refreshed_session["last_message_role"] == "assistant"
            assert "待审批动作积压" in refreshed_session["last_message_preview"]
            assert [item["role"] for item in persisted_messages] == ["user", "assistant"]
            assert persisted_messages[1]["metadata_json"]["source"] == "fallback"
    finally:
        _cleanup_agent_chat_fixture(tenant_id)


def test_agent_chat_sessions_are_isolated_by_user_and_can_be_closed():
    _ensure_agent_chat_tables_exist()
    tenant_id = f"tenant_chat_{uuid4().hex[:8]}"
    user_a = f"user_a_{uuid4().hex[:8]}"
    user_b = f"user_b_{uuid4().hex[:8]}"

    try:
        with SessionLocal() as db:
            session_a = chat_session_service.create_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_a,
                agent_scope="risk",
                title="用户A会话",
            )
            session_b = chat_session_service.create_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_b,
                agent_scope="risk",
                title="用户B会话",
            )
            chat_session_service.append_chat_message(
                db,
                tenant_id=tenant_id,
                user_id=user_a,
                session_id=session_a["session_id"],
                role="user",
                content="用户A的问题",
            )
            chat_session_service.append_chat_message(
                db,
                tenant_id=tenant_id,
                user_id=user_b,
                session_id=session_b["session_id"],
                role="user",
                content="用户B的问题",
            )

            user_a_sessions = chat_session_service.list_chat_sessions(
                db,
                tenant_id=tenant_id,
                user_id=user_a,
                agent_scope="risk",
            )
            assert [item["session_id"] for item in user_a_sessions] == [session_a["session_id"]]

            closed = chat_session_service.close_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_a,
                session_id=session_a["session_id"],
            )
            assert closed["status"] == "closed"

            active_after_close = chat_session_service.list_chat_sessions(
                db,
                tenant_id=tenant_id,
                user_id=user_a,
                agent_scope="risk",
            )
            assert active_after_close == []

            closed_messages = chat_session_service.list_chat_messages(
                db,
                tenant_id=tenant_id,
                user_id=user_a,
                session_id=session_a["session_id"],
            )
            assert closed_messages[0]["content"] == "用户A的问题"
    finally:
        _cleanup_agent_chat_fixture(tenant_id)
