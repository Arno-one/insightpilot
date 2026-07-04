from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import customer_profile_tool, intent_router, memory_service
from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.agent.platform import customer_profile_mcp_tools
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
        run_id="run_profile_demo",
        db=_DummyDb(),
    )


def _patch_profile_dependencies(monkeypatch):
    user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager",
        "permission_codes": ["crm:customer:read:self"],
    }
    monkeypatch.setattr(customer_profile_mcp_tools, "_load_current_user_context", lambda context: user)
    monkeypatch.setattr(
        customer_profile_mcp_tools.crm_service,
        "load_customer_or_404",
        lambda db, current_user, customer_id: {"customer_id": customer_id, "customer_name": "华东样例客户"},
    )
    monkeypatch.setattr(
        customer_profile_mcp_tools.memory_service,
        "build_customer_memory_snapshot",
        lambda db, **kwargs: {
            "customer_id": kwargs["customer_id"],
            "memory_scope": "customer",
            "summary_text": "华东样例客户 当前阶段为 opportunity，意向等级 high。",
            "summary_json": {
                "profile": {"customer_id": kwargs["customer_id"], "customer_name": "华东样例客户"},
                "profile_tags": {"intent_tag": "意向:high", "risk_tag": "风险:high/88"},
            },
            "source_run_id": kwargs["source_run_id"],
            "last_compiled_at": __import__("datetime").datetime(2026, 7, 4, 12, 0, 0),
        },
    )
    monkeypatch.setattr(
        customer_profile_mcp_tools.memory_service,
        "upsert_customer_memory",
        lambda db, tenant_id, memory_snapshot: {
            **memory_snapshot,
            "memory_id": "memo_profile_demo",
            "last_compiled_at": "2026-07-04T12:00:00",
        },
    )


def test_memory_service_builds_structured_profile_tags():
    summary_json = {
        "profile": {
            "lifecycle_stage": "opportunity",
            "intent_level": "high",
            "customer_level": "A",
            "competitor_involved": True,
        },
        "risk_state": {"latest_risk_level": "high", "latest_risk_score": 88},
        "follow_up_state": {"count": 4},
        "task_state": {"active_count": 1},
        "deal_state": {"latest_stage": "quotation", "latest_quote_amount": 120000},
    }

    tags = memory_service._build_profile_tags(summary_json)

    assert tags["lifecycle_tag"] == "阶段:opportunity"
    assert tags["intent_tag"] == "意向:high"
    assert tags["risk_tag"] == "风险:high/88"
    assert tags["engagement_tag"] == "互动:活跃"
    assert tags["execution_tag"] == "执行:有未完成任务"
    assert tags["competition_tag"] == "竞品:已介入"
    assert tags["deal_tag"] == "商机:quotation"
    assert tags["quote_tag"] == "报价:已报价"


def test_intent_router_detects_customer_profile_question():
    result = intent_router.route_intent("帮我生成这个客户的客户画像和标签")

    assert result.intent == intent_router.INTENT_CUSTOMER_PROFILE
    assert result.confidence >= 0.6
    assert "客户画像" in result.matched_keywords


def test_profile_generate_customer_memory_tool_writes_customer_memory(monkeypatch):
    _patch_profile_dependencies(monkeypatch)

    registry = InternalToolRegistry(customer_profile_mcp_tools.build_customer_profile_mcp_tools())
    output = registry.execute(
        "profile.generate_customer_memory",
        _tool_context(),
        {"customer_id": "cust_001"},
    )["output"]

    assert output["protocol"] == "profile.generate_customer_memory.v1"
    assert output["customer_id"] == "cust_001"
    assert output["memory"]["memory_id"] == "memo_profile_demo"
    assert output["profile_tags"]["intent_tag"] == "意向:high"


def test_shared_mcp_gateway_exposes_profile_mcp(monkeypatch):
    _patch_profile_dependencies(monkeypatch)

    gateway = build_shared_mcp_gateway()
    specs = gateway.list_tool_specs()
    result = gateway.execute("profile.generate_customer_memory", _tool_context(), {"customer_id": "cust_001"})

    assert "profile.generate_customer_memory" in {item["name"] for item in specs}
    assert result["server_name"] == "profile"
    assert result["output"]["profile_tags"]["risk_tag"] == "风险:high/88"


def test_unified_agent_chat_runs_customer_profile_generation(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []

    monkeypatch.setattr(
        customer_profile_tool,
        "run_customer_profile_tool",
        lambda db_rw, current_user, *, customer_id, runtime_context=None: {
            "reply": "客户画像已生成并写入 Customer Memory。",
            "profile_result": {
                "customer_id": customer_id,
                "profile_tags": {"intent_tag": "意向:high"},
                "summary_text": "客户画像摘要",
            },
            "customer_id": customer_id,
            "profile_tags": {"intent_tag": "意向:high"},
            "summary_text": "客户画像摘要",
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "客户画像测试",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我生成这个客户的客户画像和标签"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["intent_route"]["intent"] == "customer_profile"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "profile.generate_customer_memory"
        assert data["assistant_message"]["tool_name"] == "profile.generate_customer_memory"
        assert data["assistant_message"]["metadata_json"]["profile_tags"]["intent_tag"] == "意向:high"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)
