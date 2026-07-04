from app.modules.agent.platform import ToolExecutionContext, build_shared_mcp_gateway


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_demo",
        run_id="run_calendar_task_preview",
        db=_DummyDb(),
    )


def test_calendar_task_mcp_preview_tools_are_registered_with_safe_policy():
    registry = build_shared_mcp_gateway().list_server_registry()
    tools_by_name = {tool["name"]: tool for tool in registry["tools"]}

    task_preview = tools_by_name["task.preview_from_approval"]
    calendar_preview = tools_by_name["calendar.preview_follow_up_event"]

    assert task_preview["required_permissions"] == ["approval:review:agent_task"]
    assert task_preview["risk_level"] == "low"
    assert task_preview["side_effect"] is False
    assert task_preview["approval_required"] is False
    assert "read_only" in task_preview["governance_tags"]

    assert calendar_preview["required_permissions"] == ["approval:review:agent_task"]
    assert calendar_preview["risk_level"] == "low"
    assert calendar_preview["side_effect"] is False
    assert calendar_preview["approval_required"] is False


def test_task_mcp_preview_from_approval_returns_dry_run_trace():
    gateway = build_shared_mcp_gateway()

    result = gateway.execute(
        "task.preview_from_approval",
        _tool_context(),
        {
            "approval": {
                "approval_id": "appr_preview_001",
                "customer_id": "cust_preview_001",
                "priority": "high",
            },
            "proposed_payload": {
                "title": "安排高价值客户复盘",
                "assignee_user_id": "u_sales_001",
            },
        },
    )

    output = result["output"]
    assert output["protocol"] == "task.preview_from_approval.v1"
    assert output["task_preview"]["dry_run"] is True
    assert output["task_preview"]["source_approval_id"] == "appr_preview_001"
    assert output["trace"]["external_system"] == "not_connected"
    assert result["audit_record"]["trace_summary"] == output["trace"]


def test_calendar_mcp_preview_follow_up_event_returns_dry_run_trace():
    gateway = build_shared_mcp_gateway()

    result = gateway.execute(
        "calendar.preview_follow_up_event",
        _tool_context(),
        {
            "approval": {
                "approval_id": "appr_preview_002",
                "customer_id": "cust_preview_002",
            },
            "task": {
                "task_id": "task_preview_002",
                "title": "确认采购节奏",
                "assignee_user_id": "u_sales_002",
                "customer_id": "cust_preview_002",
            },
            "duration_minutes": 45,
        },
    )

    output = result["output"]
    assert output["protocol"] == "calendar.preview_follow_up_event.v1"
    assert output["calendar_preview"]["dry_run"] is True
    assert output["calendar_preview"]["duration_minutes"] == 45
    assert output["trace"]["task_id"] == "task_preview_002"
    assert output["trace"]["external_system"] == "not_connected"
    assert result["audit_record"]["trace_summary"] == output["trace"]
