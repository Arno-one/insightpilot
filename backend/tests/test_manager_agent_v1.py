from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import intent_router, manager_tool
from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.agent.platform import data_mcp_tools, internal_tools, manager_mcp_tools
from tests.test_agent_chat_api_v1 import _build_headers, _cleanup_agent_chat_sessions, _ensure_agent_chat_tables_exist


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_manager",
        run_id="run_manager_demo",
        db=_DummyDb(),
        readonly_db=_DummyDb(),
    )


def _patch_user_context(monkeypatch):
    user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager",
        "permission_codes": ["crm:customer:read:self", "report:read:team"],
    }
    monkeypatch.setattr(manager_mcp_tools, "_load_current_user_context", lambda context: user)
    monkeypatch.setattr(data_mcp_tools, "_load_current_user_context", lambda context: user)
    monkeypatch.setattr(internal_tools, "_load_current_user_context", lambda context: user)


def _patch_manager_dependencies(monkeypatch):
    _patch_user_context(monkeypatch)
    monkeypatch.setattr(
        data_mcp_tools.nl2sql_service,
        "query",
        lambda db_rw, db_readonly, current_user, *, question, session_id=None: {
            "session_id": session_id or "nl2sql_sess_manager",
            "query_id": "nl2sql_query_manager",
            "sql": "SELECT owner_user_name, risk_score FROM customer_risk_snapshot WHERE tenant_id = :tenant_id",
            "result": {
                "columns": ["owner_user_name", "risk_score"],
                "rows": [{"owner_user_name": "张三", "risk_score": 92}, {"owner_user_name": "李四", "risk_score": 61}],
                "row_count": 2,
            },
            "is_cached": False,
            "cost_ms": 8,
        },
    )
    monkeypatch.setattr(
        data_mcp_tools.report_service,
        "query_reports",
        lambda db, current_user, **kwargs: [
            {
                "report_id": "report_manager",
                "report_type": "weekly",
                "report_date": "2026-07-04",
                "summary": "高风险客户集中在华东区域",
                "suggestions": ["优先安排负责人回访"],
            }
        ],
    )
    monkeypatch.setattr(
        internal_tools,
        "search_customers",
        lambda db, current_user, **kwargs: {
            "bad": "shape"
        }
        and [
            {
                "customer_id": "cust_001",
                "customer_name": "华东样例客户",
                "owner_user_id": "u_sales_001",
                "owner_user_name": "张三",
            }
        ],
    )
    monkeypatch.setattr(
        internal_tools,
        "load_customer_detail_bundle",
        lambda db, current_user, customer_id, **kwargs: {
            "customer": {
                "customer_id": customer_id,
                "customer_name": "华东样例客户",
                "owner_user_id": "u_sales_001",
                "owner_user_name": "张三",
            },
            "risk_snapshots": [
                {
                    "risk_score": 92,
                    "risk_level": "high",
                    "llm_reason": "最近跟进断档且竞品介入",
                    "llm_suggestion": "负责人 24 小时内回访",
                }
            ],
            "approvals": [{"approval_id": "appr_001", "status": "pending"}],
            "tasks": [{"task_id": "task_001", "status": "pending"}],
            "report_refs": [],
        },
    )


def test_intent_router_detects_manager_decision_question():
    result = intent_router.route_intent("老板问该优先处理哪些客户，并给出建议动作")

    assert result.intent == intent_router.INTENT_MANAGER_DECISION
    assert result.confidence >= 0.6
    assert "建议动作" in result.matched_keywords


def test_manager_make_decision_tool_returns_conclusion_evidence_actions(monkeypatch):
    _patch_manager_dependencies(monkeypatch)

    registry = InternalToolRegistry(manager_mcp_tools.build_manager_mcp_tools())
    output = registry.execute("manager.make_decision", _tool_context(), {"question": "该优先处理哪些客户？"})["output"]
    decision = output["decision"]

    assert output["protocol"] == "manager.make_decision.v1"
    assert decision["protocol"] == "manager.decision.v1"
    assert decision["conclusions"]
    assert decision["evidence"]
    assert decision["recommended_actions"]
    assert decision["execution_policy"]["auto_execute"] is False
    assert decision["linked_capabilities"]["data_query"] is True
    assert decision["linked_capabilities"]["crm"] == 1
    assert decision["linked_capabilities"]["risk"] == 1
    assert decision["linked_capabilities"]["approval"] == 1
    assert decision["linked_capabilities"]["task"] == 1


def test_shared_mcp_gateway_exposes_manager_mcp(monkeypatch):
    _patch_manager_dependencies(monkeypatch)

    gateway = build_shared_mcp_gateway()
    specs = gateway.list_tool_specs()
    result = gateway.execute("manager.make_decision", _tool_context(), {"question": "哪些客户需要重点跟进？"})

    assert "manager.make_decision" in {item["name"] for item in specs}
    assert result["server_name"] == "manager"
    assert result["output"]["decision"]["recommended_actions"]


def test_unified_agent_chat_runs_manager_decision(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []

    monkeypatch.setattr(
        manager_tool,
        "run_manager_decision_tool",
        lambda db_rw, db_readonly, current_user, *, question, session_id=None, context_payload=None: {
            "reply": "经营决策建议已生成。\n\n结论\n- 优先处理华东样例客户\n依据\n- 风险：高风险\n建议动作\n- [high] 跟进高风险客户，需审批",
            "manager_result": {
                "decision": {
                    "conclusions": ["优先处理华东样例客户"],
                    "evidence": ["风险：高风险"],
                    "recommended_actions": [{"action_type": "create_follow_up_task"}],
                },
                "data_analysis": {"query": {"sql": "SELECT 1", "query_id": "q_manager", "session_id": "s_manager"}},
            },
            "tool_name": "manager.make_decision",
            "query_id": "q_manager",
            "nl2sql_session_id": "s_manager",
            "row_count": 1,
            "recommended_action_count": 1,
            "error": None,
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={"agent_scope": "manager", "intent": "unknown", "title": "经营决策测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "该优先处理哪些客户，并给出建议动作？"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["intent_route"]["intent"] == "manager_decision"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "manager.make_decision"
        assert data["assistant_message"]["tool_name"] == "manager.make_decision"
        assert data["assistant_message"]["metadata_json"]["recommended_action_count"] == 1
        assert data["assistant_message"]["metadata_json"]["decision"]["recommended_actions"]
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
