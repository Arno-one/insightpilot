from app.modules.agent import intent_router
from app.modules.agent.platform import (
    execute_agent_chat_tool,
    list_agent_chat_tool_specs,
    route_agent_chat_tool,
)
from app.modules.agent.platform import data_mcp_tools
from tests.test_data_mcp_nl2sql_v1 import _patch_user_context
from tests.test_followup_strategy_agent_v1 import _patch_followup_dependencies


class _DummyDb:
    pass


def _current_user():
    return {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager",
        "permission_codes": ["crm:customer:read:self"],
    }


def _patch_query(monkeypatch):
    monkeypatch.setattr(
        data_mcp_tools.nl2sql_service,
        "query",
        lambda db_rw, db_readonly, current_user, *, question, session_id=None: {
            "session_id": session_id or "nl2sql_sess_router",
            "query_id": "nl2sql_query_router",
            "sql": "SELECT customer_id FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 100",
            "result": {"columns": ["customer_id"], "rows": [{"customer_id": "cust_001"}], "row_count": 1},
            "is_cached": False,
            "cost_ms": 6,
        },
    )


def test_agent_chat_tool_registry_lists_three_router_tools():
    specs = list_agent_chat_tool_specs(_current_user())
    names = {item["name"] for item in specs}

    assert {"data.query_sql", "data.analyze_business", "followup.plan_strategy"}.issubset(names)
    assert all(item["router"] == "agent_chat_tool_router_v1" for item in specs)
    assert next(item for item in specs if item["name"] == "followup.plan_strategy")["requires_customer"] is True


def test_agent_chat_tool_router_selects_by_intent_scope_and_permission():
    current_user = _current_user()

    data_route = route_agent_chat_tool(
        intent=intent_router.INTENT_DATA_QUERY,
        agent_scope="general",
        current_user=current_user,
    )
    followup_route = route_agent_chat_tool(
        intent=intent_router.INTENT_FOLLOW_UP_STRATEGY,
        agent_scope="customer",
        current_user=current_user,
        has_related_customer=True,
    )
    blocked_route = route_agent_chat_tool(
        intent=intent_router.INTENT_FOLLOW_UP_STRATEGY,
        agent_scope="general",
        current_user=current_user,
        has_related_customer=False,
    )

    assert data_route.allowed is True
    assert data_route.selected_tool == "data.query_sql"
    assert followup_route.allowed is True
    assert followup_route.selected_tool == "followup.plan_strategy"
    assert blocked_route.allowed is False
    assert blocked_route.selected_tool == "followup.plan_strategy"


def test_agent_chat_tool_router_executes_three_existing_tools(monkeypatch):
    _patch_user_context(monkeypatch)
    _patch_followup_dependencies(monkeypatch)
    _patch_query(monkeypatch)
    current_user = _current_user()

    query_result = execute_agent_chat_tool(
        db_rw=_DummyDb(),
        db_readonly=_DummyDb(),
        current_user=current_user,
        run_id="run_router_query",
        intent=intent_router.INTENT_DATA_QUERY,
        agent_scope="general",
        payload={"question": "客户有哪些？"},
    )
    analysis_result = execute_agent_chat_tool(
        db_rw=_DummyDb(),
        db_readonly=_DummyDb(),
        current_user=current_user,
        run_id="run_router_analysis",
        intent=intent_router.INTENT_BUSINESS_ANALYSIS,
        agent_scope="general",
        payload={"question": "为什么客户增长放缓？"},
    )
    followup_result = execute_agent_chat_tool(
        db_rw=_DummyDb(),
        db_readonly=None,
        current_user=current_user,
        run_id="run_router_followup",
        intent=intent_router.INTENT_FOLLOW_UP_STRATEGY,
        agent_scope="customer",
        payload={"customer_id": "cust_001", "question": "怎么跟进？"},
        has_related_customer=True,
    )

    assert query_result["route"]["selected_tool"] == "data.query_sql"
    assert query_result["output"]["protocol"] == "data.query_sql.v1"
    assert analysis_result["route"]["selected_tool"] == "data.analyze_business"
    assert analysis_result["output"]["protocol"] == "data.analyze_business.v1"
    assert followup_result["route"]["selected_tool"] == "followup.plan_strategy"
    assert followup_result["output"]["protocol"] == "followup.strategy.v1"
