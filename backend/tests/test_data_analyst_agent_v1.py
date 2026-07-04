from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import intent_router
from app.modules.agent.platform import InternalToolRegistry
from app.modules.agent.platform import data_mcp_tools
from app.modules.nl2sql import service as nl2sql_service
from tests.test_agent_chat_api_v1 import _build_headers, _cleanup_agent_chat_sessions, _ensure_agent_chat_tables_exist
from tests.test_data_mcp_nl2sql_v1 import _patch_user_context, _tool_context


def _fake_revenue_query(db_rw, db_readonly, current_user, *, question, session_id=None):
    return {
        "session_id": session_id or "nl2sql_sess_revenue",
        "query_id": "nl2sql_query_revenue",
        "sql": "SELECT month, revenue FROM report_revenue WHERE tenant_id = :tenant_id ORDER BY month",
        "result": {
            "columns": ["month", "revenue"],
            "rows": [
                {"month": "2026-05", "revenue": 120000},
                {"month": "2026-06", "revenue": 90000},
                {"month": "2026-07", "revenue": 60000},
            ],
            "row_count": 3,
        },
        "is_cached": False,
        "cost_ms": 11,
    }


def test_intent_router_detects_business_analysis_question():
    result = intent_router.route_intent("为什么本月收入下降，帮我做经营分析")

    assert result.intent == intent_router.INTENT_BUSINESS_ANALYSIS
    assert result.confidence >= 0.6
    assert "为什么" in result.matched_keywords


def test_data_analyze_business_tool_returns_analysis_payload(monkeypatch):
    _patch_user_context(monkeypatch)
    monkeypatch.setattr(data_mcp_tools.nl2sql_service, "query", _fake_revenue_query)

    registry = InternalToolRegistry(data_mcp_tools.build_data_mcp_tools())
    output = registry.execute("data.analyze_business", _tool_context(), {"question": "为什么收入下降？"})["output"]

    assert output["protocol"] == "data.analyze_business.v1"
    assert output["query"]["protocol"] == "data.query_sql.v1"
    assert output["analysis"]["protocol"] == "data.analyze_business.v1"
    assert output["analysis"]["row_count"] == 3
    assert output["analysis"]["trend_insights"]
    assert output["trace"]["analysis_status"] == "generated"


def test_data_analyze_business_tool_links_recent_reports(monkeypatch):
    monkeypatch.setattr(
        data_mcp_tools,
        "_load_current_user_context",
        lambda context: {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "permission_codes": ["crm:customer:read:self", "report:read:team"],
        },
    )
    monkeypatch.setattr(data_mcp_tools.nl2sql_service, "query", _fake_revenue_query)
    monkeypatch.setattr(
        data_mcp_tools.report_service,
        "query_reports",
        lambda db, current_user, **kwargs: [
            {
                "report_id": "report_demo",
                "report_type": "monthly",
                "report_date": "2026-07-01",
                "summary": "收入下滑主要来自重点客户回款延迟",
                "suggestions": ["优先复盘高价值客户", "跟进负责人转化率"],
                "metrics_json": {},
                "risk_top_json": [],
            }
        ],
    )

    registry = InternalToolRegistry(data_mcp_tools.build_data_mcp_tools())
    output = registry.execute("data.analyze_business", _tool_context(), {"question": "为什么收入下降？"})["output"]

    assert output["trace"]["report_count"] == 1
    assert output["report_context"]["total"] == 1
    assert output["analysis"]["report_references"]
    assert "收入下滑" in output["analysis"]["report_references"][0]


def test_unified_agent_chat_runs_data_analyst_for_business_question(monkeypatch):
    _ensure_agent_chat_tables_exist()
    nl2sql_service._cache.clear()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []

    monkeypatch.setattr(data_mcp_tools.nl2sql_service, "query", _fake_revenue_query)

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={"agent_scope": "general", "intent": "unknown", "title": "经营分析 Agent 测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "为什么本月收入下降，帮我做经营分析"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["intent_route"]["intent"] == "business_analysis"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "data.analyze_business"
        assert data["assistant_message"]["tool_name"] == "data.analyze_business"
        assert "经营分析完成" in data["assistant_message"]["content"]
        assert data["assistant_message"]["metadata_json"]["analysis"]["trend_insights"]
        assert data["assistant_message"]["metadata_json"]["sql"].startswith("SELECT month")
    finally:
        nl2sql_service._cache.clear()
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
