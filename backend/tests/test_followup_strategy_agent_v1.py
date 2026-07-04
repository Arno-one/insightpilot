from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import execution_tool, followup_strategy_agent, followup_strategy_tool, intent_router
from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.agent.platform import followup_strategy_mcp_tools
from tests.test_agent_chat_api_v1 import (
    _build_headers,
    _cleanup_agent_chat_sessions,
    _cleanup_risk_chat_customer_fixture,
    _create_risk_chat_customer_fixture,
    _ensure_agent_chat_tables_exist,
)


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_manager",
        run_id="run_followup_demo",
        db=_DummyDb(),
    )


def _sample_customer_detail(now: datetime) -> dict:
    return {
        "customer": {
            "customer_id": "cust_001",
            "customer_name": "华东样例客户",
            "owner_user_id": "u_sales_001",
            "owner_user_name": "张三",
            "intent_level": "high",
            "competitor_involved": 1,
            "last_follow_up_at": now - timedelta(days=18),
        },
        "deals": [
            {
                "deal_id": "deal_001",
                "deal_name": "华东扩容项目",
                "stage": "quotation",
                "quote_amount": 168000,
                "close_result": "open",
            }
        ],
        "follow_ups": [
            {
                "follow_up_id": "fu_001",
                "occurred_at": now - timedelta(days=18),
                "sentiment": "negative",
                "next_action": "等待客户反馈",
            }
        ],
        "risk_snapshots": [
            {
                "risk_score": 86,
                "risk_level": "high",
                "llm_suggestion": "建议主管介入，确认竞品和预算口径。",
            }
        ],
        "tasks": [{"task_id": "task_001", "status": "pending"}],
        "approvals": [],
        "report_refs": [],
    }


def _patch_followup_dependencies(monkeypatch):
    now = datetime(2026, 7, 4, 12, 0, 0)
    user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager",
        "permission_codes": ["crm:customer:read:self"],
    }
    monkeypatch.setattr(followup_strategy_mcp_tools, "_load_current_user_context", lambda context: user)
    monkeypatch.setattr(
        followup_strategy_mcp_tools.crm_service,
        "load_customer_detail_bundle",
        lambda db, current_user, customer_id: _sample_customer_detail(now),
    )
    monkeypatch.setattr(
        followup_strategy_mcp_tools.memory_service,
        "load_customer_memory_map",
        lambda db, tenant_id, customer_ids: {
            "cust_001": {
                "summary_text": "客户关注预算和竞品替换风险，需要主管参与关键决策沟通。",
            }
        },
    )
    monkeypatch.setattr(
        followup_strategy_mcp_tools,
        "build_followup_strategy",
        lambda customer_detail, **kwargs: followup_strategy_agent.build_followup_strategy(
            customer_detail,
            now=now,
            **kwargs,
        ),
    )


def test_followup_strategy_agent_builds_rescue_strategy():
    now = datetime(2026, 7, 4, 12, 0, 0)

    result = followup_strategy_agent.build_followup_strategy(
        _sample_customer_detail(now),
        customer_memory={"summary_text": "客户关注预算和竞品替换风险。"},
        now=now,
    )

    assert result["protocol"] == "followup.strategy.v1"
    assert result["strategy_level"] == "rescue"
    assert result["priority"] == "high"
    assert result["recommended_action_count"] == 1
    assert result["recommended_actions"][0]["source"] == "follow_up_strategy"
    assert "竞品" in "；".join(result["talking_points"])


def test_intent_router_detects_followup_strategy_question():
    result = intent_router.route_intent("帮我生成这个客户的跟进策略和回访话术")

    assert result.intent == intent_router.INTENT_FOLLOW_UP_STRATEGY
    assert result.confidence >= 0.6
    assert "跟进策略" in result.matched_keywords


def test_followup_plan_strategy_tool_returns_recommended_actions(monkeypatch):
    _patch_followup_dependencies(monkeypatch)

    registry = InternalToolRegistry(followup_strategy_mcp_tools.build_followup_strategy_mcp_tools())
    output = registry.execute("followup.plan_strategy", _tool_context(), {"customer_id": "cust_001"})["output"]

    assert output["protocol"] == "followup.strategy.v1"
    assert output["trace"]["memory_hit"] is True
    assert output["recommended_actions"][0]["requires_approval"] is True


def test_shared_mcp_gateway_exposes_followup_strategy_mcp(monkeypatch):
    _patch_followup_dependencies(monkeypatch)

    gateway = build_shared_mcp_gateway()
    specs = gateway.list_tool_specs()
    result = gateway.execute("followup.plan_strategy", _tool_context(), {"customer_id": "cust_001"})

    assert "followup.plan_strategy" in {item["name"] for item in specs}
    assert result["server_name"] == "followup"
    assert result["output"]["recommended_action_count"] == 1


def test_unified_agent_chat_runs_followup_strategy(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []

    monkeypatch.setattr(
        followup_strategy_tool,
        "run_followup_strategy_tool",
        lambda db_rw, current_user, *, customer_id, question: {
            "reply": "跟进策略已生成。\n\n建议动作\n- [high] 执行抢救式跟进，需审批",
            "strategy_result": {
                "protocol": "followup.strategy.v1",
                "customer_id": customer_id,
                "strategy_level": "rescue",
                "recommended_actions": [{"source": "follow_up_strategy", "customer_id": customer_id, "requires_approval": True}],
                "recommended_action_count": 1,
            },
            "tool_name": "followup.plan_strategy",
            "customer_id": customer_id,
            "strategy_level": "rescue",
            "recommended_actions": [{"source": "follow_up_strategy", "customer_id": customer_id, "requires_approval": True}],
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
                "title": "跟进策略测试",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我生成这个客户的跟进策略和回访话术"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["intent_route"]["intent"] == "follow_up_strategy"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "followup.plan_strategy"
        assert data["assistant_message"]["tool_name"] == "followup.plan_strategy"
        assert data["assistant_message"]["metadata_json"]["recommended_action_count"] == 1
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_unified_agent_chat_submits_followup_strategy_actions_to_approval(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []
    actions = [
        {
            "action_type": "create_follow_up_task",
            "source": "follow_up_strategy",
            "priority": "high",
            "customer_id": customer_id,
            "title": "执行抢救式跟进",
            "reason": "客户风险高且竞品介入",
            "requires_approval": True,
        }
    ]

    monkeypatch.setattr(
        followup_strategy_tool,
        "run_followup_strategy_tool",
        lambda db_rw, current_user, *, customer_id, question: {
            "reply": "跟进策略已生成。",
            "strategy_result": {
                "protocol": "followup.strategy.v1",
                "customer_id": customer_id,
                "strategy_level": "rescue",
                "recommended_actions": actions,
                "recommended_action_count": 1,
            },
            "tool_name": "followup.plan_strategy",
            "customer_id": customer_id,
            "strategy_level": "rescue",
            "recommended_actions": actions,
            "recommended_action_count": 1,
            "error": None,
        },
    )
    monkeypatch.setattr(
        execution_tool,
        "run_execution_proposal_tool",
        lambda db_rw, current_user, *, actions: {
            "reply": "已生成 1 个执行审批草稿，审批通过后才会触发动作链。",
            "execution_result": {"proposal": {"approval_count": 1, "source_actions": actions}},
            "approval_count": 1,
            "approvals": [{"approval_id": "appr_followup_1", "status": "pending"}],
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "跟进策略审批测试",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        strategy_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我生成跟进策略"},
        )
        assert strategy_response.status_code == 200
        assert strategy_response.json()["data"]["runtime"]["handler"] == "followup.plan_strategy"

        execution_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "把刚才的跟进策略提交审批"},
        )
        assert execution_response.status_code == 200
        data = execution_response.json()["data"]

        assert data["intent_route"]["intent"] == "action_execution"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "execution.propose_actions"
        assert data["runtime"]["execution"]["proposal"]["source_actions"][0]["source"] == "follow_up_strategy"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)
