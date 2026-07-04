from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent import chat_session_service, conversation_memory_service
from app.modules.memory import service as memory_service
from app.modules.nl2sql import service as nl2sql_service


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.store[key] = value

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


def _cleanup_short_term_memory_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM agent_chat_message WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM agent_chat_session WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM nl2sql_message WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM nl2sql_query_audit WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM nl2sql_session WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_short_term_memory_standardizes_agent_nl2sql_and_risk_chat_sources():
    tenant_id = f"tenant_short_memory_{uuid4().hex[:8]}"
    user_id = f"user_short_memory_{uuid4().hex[:8]}"
    current_user = {"tenant_id": tenant_id, "user_id": user_id}
    fake_redis = _FakeRedis()
    _cleanup_short_term_memory_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            agent_session = chat_session_service.create_chat_session(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_scope="general",
                intent="business_analysis",
                title="经营分析对话",
                context_json={"entry": "agent_chat"},
            )
            chat_session_service.append_chat_message(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=agent_session["session_id"],
                role="user",
                content="分析本月经营指标",
                intent="business_analysis",
            )

            nl2sql_session = nl2sql_service.create_session(
                db,
                current_user,
                title="数据问答",
                data_scope="self",
                context_json={"entry": "nl2sql"},
            )
            nl2sql_service.append_message(
                db,
                current_user,
                session_id=nl2sql_session["session_id"],
                role="user",
                content="统计本月客户数",
                query_id="query_short_memory",
            )

            risk_memory, _ = conversation_memory_service.append_conversation_messages(
                tenant_id,
                user_id,
                "cust_short_memory",
                messages=[
                    {"role": "user", "content": "这个客户风险为什么升高？"},
                    {"role": "assistant", "content": "主要因为跟进断档和竞品介入。"},
                ],
                redis_client=fake_redis,
            )
            conversation_memory_service.upsert_conversation_session_index(
                tenant_id,
                user_id,
                customer_id="cust_short_memory",
                customer_name="短期记忆测试客户",
                session_key=risk_memory["session_key"],
                recent_messages=risk_memory["recent_messages"],
                updated_at=risk_memory["updated_at"],
                latest_risk_level="high",
                redis_client=fake_redis,
            )

            sessions = memory_service.list_short_term_sessions(
                db,
                current_user,
                redis_client=fake_redis,
            )
            agent_detail = memory_service.load_short_term_memory(
                db,
                current_user,
                source_type="agent_chat",
                session_id=agent_session["session_id"],
            )
            nl2sql_detail = memory_service.load_short_term_memory(
                db,
                current_user,
                source_type="nl2sql",
                session_id=nl2sql_session["session_id"],
            )
            risk_detail = memory_service.load_short_term_memory(
                db,
                current_user,
                source_type="risk_chat",
                session_id="cust_short_memory",
                redis_client=fake_redis,
            )
            summary = memory_service.summarize_short_term_memory(
                db,
                current_user,
                redis_client=fake_redis,
            )

        source_types = {item["source_type"] for item in sessions}
        assert source_types == {"agent_chat", "nl2sql", "risk_chat"}
        assert all("memory_id" in item for item in sessions)
        assert agent_detail["session"]["scope"] == "general"
        assert agent_detail["messages"][0]["intent"] == "business_analysis"
        assert nl2sql_detail["session"]["scope"] == "self"
        assert nl2sql_detail["messages"][0]["tool_name"] == "nl2sql.query"
        assert risk_detail["session"]["related_entity_id"] == "cust_short_memory"
        assert risk_detail["session"]["message_count"] == 2
        assert risk_detail["messages"][1]["role"] == "assistant"
        assert summary["session_count"] == 3
        assert summary["by_source"] == {"agent_chat": 1, "risk_chat": 1, "nl2sql": 1}
    finally:
        _cleanup_short_term_memory_fixture(tenant_id)
