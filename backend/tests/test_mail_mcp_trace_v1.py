from app.modules.agent.platform import ToolExecutionContext, build_shared_mcp_gateway
from app.modules.notification import service as notification_service


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_demo",
        run_id="run_mail_trace",
        db=_DummyDb(),
    )


def test_mail_mcp_send_task_assignment_returns_trace_for_gateway_audit(monkeypatch):
    monkeypatch.setattr(
        notification_service,
        "create_task_assignment_notification",
        lambda db, tenant_id, approval, task, sender_user_id, happened_at=None: {
            "notification_id": "notify_trace_001",
            "approval_id": approval["approval_id"],
            "task_id": task["task_id"],
            "delivery_status": "sent",
            "retry_count": 0,
        },
    )

    gateway = build_shared_mcp_gateway()
    result = gateway.execute(
        "mail.send_task_assignment",
        _tool_context(),
        {
            "approval": {
                "approval_id": "appr_trace_001",
                "approval_type": "agent_task_draft",
                "status": "approved",
                "customer_id": "cust_trace_001",
                "run_id": "run_source_001",
            },
            "task": {
                "task_id": "task_trace_001",
                "assignee_user_id": "u_sales_001",
                "customer_id": "cust_trace_001",
            },
        },
    )

    output = result["output"]
    trace = output["trace"]

    assert output["protocol"] == "mail.send_task_assignment.v1"
    assert trace["tool_name"] == "mail.send_task_assignment"
    assert trace["notification_id"] == "notify_trace_001"
    assert trace["approval"]["approval_id"] == "appr_trace_001"
    assert trace["task"]["task_id"] == "task_trace_001"
    assert result["audit_record"]["trace_summary"] == trace


def test_mail_mcp_retry_failed_delivery_returns_trace_summary(monkeypatch):
    monkeypatch.setattr(
        notification_service,
        "load_notification_operator_context",
        lambda db, tenant_id, user_id: {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "permission_codes": ["task:read:team"],
        },
    )
    monkeypatch.setattr(
        notification_service,
        "retry_notification_delivery",
        lambda db, current_user, notification_id, happened_at=None: {
            "notification_id": notification_id,
            "delivery_status": "sent_after_retry",
            "retry_count": 2,
        },
    )

    gateway = build_shared_mcp_gateway()
    result = gateway.execute(
        "mail.retry_failed_delivery",
        _tool_context(),
        {"notification_id": "notify_retry_001"},
    )

    output = result["output"]
    assert output["protocol"] == "mail.retry_failed_delivery.v1"
    assert output["trace"]["delivery_status"] == "sent_after_retry"
    assert result["audit_record"]["trace_summary"]["notification_id"] == "notify_retry_001"
