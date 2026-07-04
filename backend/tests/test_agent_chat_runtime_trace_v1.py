from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.agent import followup_strategy_tool
from tests.test_agent_chat_api_v1 import (
    _build_headers,
    _cleanup_agent_chat_sessions,
    _cleanup_risk_chat_customer_fixture,
    _create_risk_chat_customer_fixture,
    _ensure_agent_chat_tables_exist,
)


def _cleanup_agent_runtime_trace(tenant_id: str, run_id: str | None):
    if not run_id:
        return
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM agent_step WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.execute(
            text("DELETE FROM agent_run WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.commit()


def test_unified_agent_chat_runtime_writes_agent_trace(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []
    run_id: str | None = None

    monkeypatch.setattr(
        followup_strategy_tool,
        "run_followup_strategy_tool",
        lambda db_rw, current_user, *, customer_id, question: {
            "reply": "跟进策略已生成。",
            "strategy_result": {
                "protocol": "followup.strategy.v1",
                "customer_id": customer_id,
                "strategy_level": "rescue",
                "recommended_actions": [
                    {
                        "source": "follow_up_strategy",
                        "customer_id": customer_id,
                        "requires_approval": True,
                    }
                ],
                "recommended_action_count": 1,
            },
            "tool_name": "followup.plan_strategy",
            "customer_id": customer_id,
            "strategy_level": "rescue",
            "recommended_actions": [
                {
                    "source": "follow_up_strategy",
                    "customer_id": customer_id,
                    "requires_approval": True,
                }
            ],
            "recommended_action_count": 1,
            "error": None,
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "统一对话 Trace 测试",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我生成这个客户的跟进策略"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]
        run_id = data["assistant_message"]["run_id"]

        assert data["runtime"]["run_id"] == run_id
        assert data["assistant_message"]["metadata_json"]["runtime_run_id"] == run_id
        assert data["assistant_message"]["metadata_json"]["runtime_step_id"].startswith("step_")

        detail_response = client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["run"]["run_type"] == "agent_chat_runtime"
        assert detail["run"]["graph_name"] == "unified_agent_chat_runtime"
        assert detail["run"]["status"] == "success"
        assert detail["steps"][0]["node_name"] == "agent_chat_tool"
        assert detail["steps"][0]["tool_name"] == "followup.plan_strategy"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_agent_runtime_trace(tenant_id, run_id)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)
