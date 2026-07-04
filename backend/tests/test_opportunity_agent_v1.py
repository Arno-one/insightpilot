from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import execution_tool, intent_router, opportunity_agent, opportunity_tool
from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.agent.platform import opportunity_mcp_tools
from tests.test_agent_chat_api_v1 import _build_headers, _cleanup_agent_chat_sessions, _ensure_agent_chat_tables_exist


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_manager",
        run_id="run_opportunity_demo",
        db=_DummyDb(),
    )


def _sample_rows(now: datetime) -> list[dict]:
    return [
        {
            "deal_id": "deal_hot_001",
            "customer_id": "cust_001",
            "customer_name": "华东样例客户",
            "owner_user_id": "u_sales_001",
            "owner_user_name": "张三",
            "deal_name": "华东扩容项目",
            "stage": "quotation",
            "amount": 180000,
            "quote_amount": 168000,
            "quoted_at": now - timedelta(days=10),
            "intent_level": "high",
            "competitor_involved": 0,
            "last_follow_up_at": now - timedelta(days=3),
            "close_result": "open",
        },
        {
            "deal_id": "deal_risk_001",
            "customer_id": "cust_002",
            "customer_name": "华南风险客户",
            "owner_user_id": "u_sales_002",
            "owner_user_name": "李四",
            "deal_name": "华南替换项目",
            "stage": "solution",
            "amount": 90000,
            "quote_amount": None,
            "quoted_at": None,
            "intent_level": "medium",
            "competitor_involved": 1,
            "last_follow_up_at": now - timedelta(days=20),
            "close_result": "open",
        },
    ]


def _patch_opportunity_dependencies(monkeypatch):
    now = datetime(2026, 7, 4, 12, 0, 0)
    user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager",
        "permission_codes": ["crm:customer:read:self"],
    }
    monkeypatch.setattr(opportunity_mcp_tools, "_load_current_user_context", lambda context: user)
    monkeypatch.setattr(opportunity_mcp_tools, "_load_opportunity_rows", lambda context, current_user, payload: _sample_rows(now))
    monkeypatch.setattr(opportunity_mcp_tools, "analyze_opportunities", lambda rows, **kwargs: opportunity_agent.analyze_opportunities(rows, now=now, **kwargs))


def test_opportunity_agent_detects_quote_timeout_and_heat_change():
    now = datetime(2026, 7, 4, 12, 0, 0)

    result = opportunity_agent.analyze_opportunities(_sample_rows(now), now=now)

    assert result["protocol"] == "opportunity.scan.v1"
    assert result["total"] == 2
    assert result["quote_timeout_count"] == 1
    assert result["heat_change_count"] == 2
    assert result["priority_items"][0]["deal_id"] == "deal_hot_001"
    assert result["priority_items"][0]["quote_timeout"] is True
    assert "报价后 10 天未记录有效响应" in result["priority_items"][0]["alerts"]
    assert result["recommended_action_count"] == 2
    assert result["recommended_actions"][0]["source"] == "opportunity_scan"
    assert result["recommended_actions"][0]["requires_approval"] is True


def test_intent_router_detects_opportunity_analysis_question():
    result = intent_router.route_intent("帮我做一下商机分析，看看哪些报价超时以及成交概率变化")

    assert result.intent == intent_router.INTENT_OPPORTUNITY_ANALYSIS
    assert result.confidence >= 0.6
    assert "商机分析" in result.matched_keywords


def test_opportunity_scan_tool_returns_priority_items(monkeypatch):
    _patch_opportunity_dependencies(monkeypatch)

    registry = InternalToolRegistry(opportunity_mcp_tools.build_opportunity_mcp_tools())
    output = registry.execute("opportunity.scan", _tool_context(), {"question": "扫描商机"})["output"]

    assert output["protocol"] == "opportunity.scan.v1"
    assert output["execution_policy"]["auto_execute"] is False
    assert output["quote_timeout_count"] == 1
    assert output["priority_items"][0]["follow_up_suggestion"]
    assert output["recommended_action_count"] == 2


def test_shared_mcp_gateway_exposes_opportunity_mcp(monkeypatch):
    _patch_opportunity_dependencies(monkeypatch)

    gateway = build_shared_mcp_gateway()
    specs = gateway.list_tool_specs()
    result = gateway.execute("opportunity.scan", _tool_context(), {"question": "扫描商机"})

    assert "opportunity.scan" in {item["name"] for item in specs}
    assert result["server_name"] == "opportunity"
    assert result["output"]["priority_items"]


def test_unified_agent_chat_runs_opportunity_scan(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []

    monkeypatch.setattr(
        opportunity_tool,
        "run_opportunity_scan_tool",
        lambda db_rw, current_user, *, question, customer_id=None, owner_user_id=None, limit=50, quote_timeout_days=7: {
            "reply": "商机分析已生成。\n\n结论\n- 扫描 2 个商机，发现 1 个报价超时、2 个热度变化信号。",
            "opportunity_result": {
                "protocol": "opportunity.scan.v1",
                "total": 2,
                "quote_timeout_count": 1,
                "heat_change_count": 2,
                "priority_items": [{"deal_id": "deal_hot_001", "follow_up_suggestion": "优先回访报价反馈"}],
                "recommended_actions": [
                    {
                        "action_type": "create_follow_up_task",
                        "source": "opportunity_scan",
                        "priority": "high",
                        "customer_id": "cust_001",
                        "title": "跟进重点商机：华东样例客户 / 华东扩容项目",
                        "reason": "报价超时",
                        "requires_approval": True,
                    }
                ],
            },
            "tool_name": "opportunity.scan",
            "total": 2,
            "quote_timeout_count": 1,
            "heat_change_count": 2,
            "priority_count": 1,
            "recommended_actions": [
                {
                    "action_type": "create_follow_up_task",
                    "source": "opportunity_scan",
                    "priority": "high",
                    "customer_id": "cust_001",
                    "title": "跟进重点商机：华东样例客户 / 华东扩容项目",
                    "reason": "报价超时",
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
            json={"agent_scope": "sales", "intent": "unknown", "title": "商机分析测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我做商机分析，看看报价超时和成交概率"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["intent_route"]["intent"] == "opportunity_analysis"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "opportunity.scan"
        assert data["assistant_message"]["tool_name"] == "opportunity.scan"
        assert data["assistant_message"]["metadata_json"]["quote_timeout_count"] == 1
        assert data["assistant_message"]["metadata_json"]["opportunity"]["priority_items"]
        assert data["assistant_message"]["metadata_json"]["recommended_action_count"] == 1
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)


def test_unified_agent_chat_submits_opportunity_actions_to_approval(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []
    opportunity_actions = [
        {
            "action_type": "create_follow_up_task",
            "source": "opportunity_scan",
            "priority": "high",
            "customer_id": "cust_001",
            "customer_name": "华东样例客户",
            "deal_id": "deal_hot_001",
            "deal_name": "华东扩容项目",
            "owner_user_id": "u_sales_001",
            "title": "跟进重点商机：华东样例客户 / 华东扩容项目",
            "reason": "报价后 10 天未记录有效响应",
            "recommended_script": "优先回访报价反馈",
            "requires_approval": True,
        }
    ]

    monkeypatch.setattr(
        opportunity_tool,
        "run_opportunity_scan_tool",
        lambda db_rw, current_user, *, question, customer_id=None, owner_user_id=None, limit=50, quote_timeout_days=7: {
            "reply": "商机分析已生成。\n\n建议动作\n- 优先回访报价反馈",
            "opportunity_result": {
                "protocol": "opportunity.scan.v1",
                "total": 1,
                "quote_timeout_count": 1,
                "heat_change_count": 1,
                "priority_items": [{"deal_id": "deal_hot_001"}],
                "recommended_actions": opportunity_actions,
                "recommended_action_count": 1,
            },
            "tool_name": "opportunity.scan",
            "total": 1,
            "quote_timeout_count": 1,
            "heat_change_count": 1,
            "priority_count": 1,
            "recommended_actions": opportunity_actions,
            "recommended_action_count": 1,
            "error": None,
        },
    )
    monkeypatch.setattr(
        execution_tool,
        "run_execution_proposal_tool",
        lambda db_rw, current_user, *, actions: {
            "reply": "已生成 1 个执行审批草稿，审批通过后才会触发动作链。",
            "execution_result": {
                "proposal": {
                    "approval_count": 1,
                    "approvals": [{"approval_id": "appr_opp_1", "status": "pending"}],
                    "source_actions": actions,
                }
            },
            "approval_count": 1,
            "approvals": [{"approval_id": "appr_opp_1", "status": "pending"}],
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={"agent_scope": "sales", "intent": "unknown", "title": "商机执行闭环测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        opportunity_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我做商机分析，看看哪些报价超时"},
        )
        assert opportunity_response.status_code == 200
        assert opportunity_response.json()["data"]["runtime"]["handler"] == "opportunity.scan"

        execution_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "把刚才的商机跟进建议提交审批"},
        )
        assert execution_response.status_code == 200
        data = execution_response.json()["data"]

        assert data["intent_route"]["intent"] == "action_execution"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "execution.propose_actions"
        assert data["assistant_message"]["metadata_json"]["approval_count"] == 1
        assert data["runtime"]["execution"]["proposal"]["source_actions"][0]["source"] == "opportunity_scan"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
