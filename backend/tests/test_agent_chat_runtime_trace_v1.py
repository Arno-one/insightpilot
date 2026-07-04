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


def test_unified_agent_chat_runtime_writes_failed_agent_trace(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []
    run_id: str | None = None

    def raise_followup_error(*args, **kwargs):
        raise RuntimeError("策略工具模拟失败")

    monkeypatch.setattr(followup_strategy_tool, "run_followup_strategy_tool", raise_followup_error)

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "统一对话失败 Trace 测试",
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

        assert data["runtime"]["status"] == "failed"
        assert data["runtime"]["run_id"] == run_id
        assert "策略工具模拟失败" in data["runtime"]["error"]
        assert data["runtime"]["recovery_plan"][0]["action"] == "inspect_trace"
        assert data["assistant_message"]["metadata_json"]["runtime_status"] == "failed"
        assert data["assistant_message"]["metadata_json"]["recovery_plan"]

        detail_response = client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["run"]["run_type"] == "agent_chat_runtime"
        assert detail["run"]["status"] == "failed"
        assert "策略工具模拟失败" in detail["run"]["error_message"]
        assert detail["run"]["output_json"]["recovery_plan"][0]["action"] == "inspect_trace"
        assert detail["steps"][0]["status"] == "failed"
        assert detail["steps"][0]["tool_name"] == "followup.plan_strategy"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_agent_runtime_trace(tenant_id, run_id)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_agent_chat_recovery_event_is_persisted_as_system_message():
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _user_id = _build_headers(client)
    session_ids: list[str] = []

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "general",
                "intent": "unknown",
                "title": "recovery event test",
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        event_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/recovery-events",
            headers=headers,
            json={
                "action": "retry",
                "title": "Retry failed runtime",
                "status": "succeeded",
                "source_run_id": "run_failed_demo",
                "new_run_id": "run_retry_demo",
                "metadata_json": {"from_test": True},
            },
        )
        assert event_response.status_code == 200
        event_message = event_response.json()["data"]

        assert event_message["role"] == "system"
        assert event_message["tool_name"] == "agent_chat.recovery_event"
        assert event_message["run_id"] == "run_retry_demo"
        assert event_message["metadata_json"]["runtime_handler"] == "agent_chat.recovery_event"
        assert event_message["metadata_json"]["recovery_event"]["status"] == "succeeded"
        assert event_message["metadata_json"]["recovery_event"]["source_run_id"] == "run_failed_demo"
        assert event_message["metadata_json"]["from_test"] is True

        detail_response = client.get(f"/api/agent/chat/sessions/{session_id}", headers=headers)
        assert detail_response.status_code == 200
        detail_data = detail_response.json()["data"]
        messages = detail_data["messages"]
        assert messages[-1]["message_id"] == event_message["message_id"]
        assert messages[-1]["metadata_json"]["recovery_event"]["new_run_id"] == "run_retry_demo"
        assert detail_data["recovery_event_summary"]["total"] == 1
        assert detail_data["recovery_event_summary"]["succeeded_count"] == 1
        assert detail_data["recovery_event_summary"]["last_event"]["new_run_id"] == "run_retry_demo"

        list_response = client.get("/api/agent/chat/sessions?limit=20", headers=headers)
        assert list_response.status_code == 200
        listed_session = next(item for item in list_response.json()["data"] if item["session_id"] == session_id)
        assert listed_session["recovery_event_summary"]["total"] == 1
        assert listed_session["recovery_event_summary"]["last_event"]["status"] == "succeeded"

        succeeded_response = client.get("/api/agent/chat/sessions?recovery_status=succeeded&limit=20", headers=headers)
        assert succeeded_response.status_code == 200
        assert any(item["session_id"] == session_id for item in succeeded_response.json()["data"])

        failed_response = client.get("/api/agent/chat/sessions?recovery_status=failed&limit=20", headers=headers)
        assert failed_response.status_code == 200
        assert all(item["session_id"] != session_id for item in failed_response.json()["data"])

        events_response = client.get(f"/api/agent/chat/sessions/{session_id}/recovery-events", headers=headers)
        assert events_response.status_code == 200
        events = events_response.json()["data"]
        assert len(events) == 1
        assert events[0]["message_id"] == event_message["message_id"]
        assert events[0]["recovery_event"]["new_run_id"] == "run_retry_demo"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
