from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import intent_router, opportunity_agent, opportunity_tool
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
            },
            "tool_name": "opportunity.scan",
            "total": 2,
            "quote_timeout_count": 1,
            "heat_change_count": 2,
            "priority_count": 1,
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
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
