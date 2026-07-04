from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import followup_strategy_tool
from tests.test_agent_chat_api_v1 import (
    _build_headers,
    _cleanup_agent_chat_sessions,
    _cleanup_risk_chat_customer_fixture,
    _create_risk_chat_customer_fixture,
    _ensure_agent_chat_tables_exist,
)
from tests.test_agent_chat_runtime_trace_v1 import _cleanup_agent_runtime_trace, _ensure_agent_runtime_plan_tables_exist


def test_runtime_orchestration_stage_main_chain_regression(monkeypatch):
    """阶段级回归：统一覆盖计划、工具路由、执行、Coordinator 和 Trace 查询主链路。"""
    _ensure_agent_chat_tables_exist()
    _ensure_agent_runtime_plan_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []
    run_id: str | None = None

    monkeypatch.setattr(
        followup_strategy_tool,
        "run_followup_strategy_tool",
        lambda db_rw, current_user, *, customer_id, question: {
            "reply": "阶段回归：跟进策略已生成。",
            "strategy_result": {
                "protocol": "followup.strategy.v1",
                "customer_id": customer_id,
                "strategy_level": "rescue",
                "recommended_actions": [],
                "recommended_action_count": 0,
            },
            "tool_name": "followup.plan_strategy",
            "tool_route": {
                "router": "agent_chat_tool_router_v1",
                "intent": "follow_up_strategy",
                "agent_scope": "customer",
                "selected_tool": "followup.plan_strategy",
                "required_permissions": ["crm:customer:read:self"],
                "allowed": True,
                "reason": "阶段回归命中工具",
                "matched_policy": "follow_up_strategy",
                "available_tools": ["data.query_sql", "data.analyze_business", "followup.plan_strategy"],
            },
            "customer_id": customer_id,
            "strategy_level": "rescue",
            "recommended_actions": [],
            "recommended_action_count": 0,
            "error": None,
        },
    )

    try:
        tools_response = client.get("/api/agent/chat/tools", headers=headers)
        assert tools_response.status_code == 200
        tool_names = {item["name"] for item in tools_response.json()["data"]}
        assert {"data.query_sql", "data.analyze_business", "followup.plan_strategy"}.issubset(tool_names)

        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "Runtime 编排阶段回归",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "生成这个客户的跟进策略"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]
        run_id = data["runtime"]["run_id"]

        assert data["runtime"]["handler"] == "followup.plan_strategy"
        assert data["runtime"]["planner"]["planner"] == "template_planner_v1"
        assert data["runtime"]["tool_route"]["selected_tool"] == "followup.plan_strategy"
        assert data["runtime"]["coordinator"]["referenced_step_ids"] == data["runtime"]["step_ids"][:4]
        assert len(data["runtime"]["step_ids"]) == 5

        detail_response = client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert [step["node_name"] for step in detail["steps"]] == [
            "agent_chat_intent_route",
            "agent_chat_planner",
            "agent_chat_tool_router",
            "agent_chat_tool",
            "agent_chat_coordinator",
        ]
        assert detail["plans"][0]["metadata_json"]["step_count"] == 5
        assert [step["step_code"] for step in detail["plans"][0]["steps"]] == [
            "intent_route",
            "template_planner",
            "tool_router",
            "tool_handler",
            "coordinator",
        ]
        assert [item["event_type"] for item in detail["timeline"]].count("step") == 5
        assert {"run", "plan", "step"}.issubset({item["event_type"] for item in detail["timeline"]})
        assert any(item["title"] == "agent_chat_coordinator" for item in detail["timeline"])
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_agent_runtime_trace(tenant_id, run_id)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)
