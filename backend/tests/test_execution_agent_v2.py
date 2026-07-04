from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent import execution_tool, intent_router, manager_tool
from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.agent.platform import execution_mcp_tools, internal_tools
from tests.test_agent_chat_api_v1 import _build_headers, _cleanup_agent_chat_sessions, _ensure_agent_chat_tables_exist


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_manager",
        run_id="run_execution_demo",
        db=_DummyDb(),
    )


def _patch_execution_user(monkeypatch):
    user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager",
        "permission_codes": ["crm:customer:read:self"],
    }
    monkeypatch.setattr(execution_mcp_tools, "_load_current_user_context", lambda context: user)


def _patch_approval_create(monkeypatch):
    created: list[dict] = []

    def fake_create_approval_draft(db, **kwargs):
        created.append(kwargs)
        return {
            "approval_id": f"appr_exec_{len(created)}",
            "approval_type": kwargs.get("approval_type"),
            "customer_id": kwargs["customer_id"],
            "status": "pending",
            "proposed_payload_json": kwargs["proposed_payload"],
        }

    monkeypatch.setattr(internal_tools, "create_approval_draft", fake_create_approval_draft)
    return created


def _sample_actions():
    return [
        {
            "action_type": "create_follow_up_task",
            "priority": "high",
            "customer_id": "cust_001",
            "customer_name": "华东样例客户",
            "owner_user_id": "u_sales_001",
            "title": "跟进高风险客户",
            "reason": "客户风险分偏高，需要负责人回访。",
            "requires_approval": True,
        },
        {
            "action_type": "review_open_tasks",
            "priority": "medium",
            "title": "复核未完成任务",
            "requires_approval": False,
        },
    ]


def test_intent_router_detects_action_execution_question():
    result = intent_router.route_intent("把刚才的建议动作提交审批，并创建任务")

    assert result.intent == intent_router.INTENT_ACTION_EXECUTION
    assert result.confidence >= 0.6
    assert "提交审批" in result.matched_keywords


def test_execution_propose_actions_creates_approval_drafts(monkeypatch):
    _patch_execution_user(monkeypatch)
    created = _patch_approval_create(monkeypatch)

    registry = InternalToolRegistry(execution_mcp_tools.build_execution_mcp_tools())
    output = registry.execute("execution.propose_actions", _tool_context(), {"actions": _sample_actions()})["output"]
    proposal = output["proposal"]

    assert output["protocol"] == "execution.propose_actions.v1"
    assert proposal["protocol"] == "execution.proposal.v1"
    assert proposal["requested_action_count"] == 1
    assert proposal["approval_count"] == 1
    assert proposal["execution_boundary"]["auto_execute"] is False
    assert proposal["execution_boundary"]["next_step"].startswith("人工审批通过后")
    assert created[0]["approval_type"] == "agent_execution_draft"
    assert created[0]["proposed_payload"]["title"] == "跟进高风险客户"


def test_shared_mcp_gateway_exposes_execution_mcp(monkeypatch):
    _patch_execution_user(monkeypatch)
    _patch_approval_create(monkeypatch)

    gateway = build_shared_mcp_gateway()
    specs = gateway.list_tool_specs()
    result = gateway.execute("execution.propose_actions", _tool_context(), {"actions": _sample_actions()})

    assert "execution.propose_actions" in {item["name"] for item in specs}
    assert result["server_name"] == "execution"
    assert result["output"]["proposal"]["approval_count"] == 1


def test_unified_agent_chat_submits_previous_manager_actions_to_approval(monkeypatch):
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []

    monkeypatch.setattr(
        manager_tool,
        "run_manager_decision_tool",
        lambda db_rw, db_readonly, current_user, *, question, session_id=None, context_payload=None: {
            "reply": "经营决策建议已生成。\n\n建议动作\n- [high] 跟进高风险客户，需审批",
            "manager_result": {
                "decision": {
                    "conclusions": ["优先处理华东样例客户"],
                    "evidence": ["风险：高风险"],
                    "recommended_actions": _sample_actions(),
                },
                "data_analysis": {"query": {"sql": "SELECT 1", "query_id": "q_manager", "session_id": "s_manager"}},
            },
            "tool_name": "manager.make_decision",
            "query_id": "q_manager",
            "nl2sql_session_id": "s_manager",
            "row_count": 1,
            "recommended_action_count": 2,
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
                    "approvals": [{"approval_id": "appr_exec_1", "status": "pending"}],
                }
            },
            "approval_count": 1,
            "approvals": [{"approval_id": "appr_exec_1", "status": "pending"}],
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={"agent_scope": "manager", "intent": "unknown", "title": "执行建议测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        manager_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "该优先处理哪些客户，并给出建议动作？"},
        )
        assert manager_response.status_code == 200
        assert manager_response.json()["data"]["runtime"]["handler"] == "manager.make_decision"

        execution_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "把刚才的建议动作提交审批"},
        )
        assert execution_response.status_code == 200
        data = execution_response.json()["data"]

        assert data["intent_route"]["intent"] == "action_execution"
        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "execution.propose_actions"
        assert data["assistant_message"]["tool_name"] == "execution.propose_actions"
        assert data["assistant_message"]["metadata_json"]["approval_count"] == 1
        assert data["assistant_message"]["metadata_json"]["approvals"][0]["approval_id"] == "appr_exec_1"
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
