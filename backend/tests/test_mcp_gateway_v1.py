from app.modules.agent.platform import MCPGateway, MCPServerAdapter, MCPToolDefinition, ToolExecutionContext, build_shared_mcp_gateway
from app.modules.agent.platform import internal_tools


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_demo",
        run_id="run_demo",
        db=_DummyDb(),
    )


def test_mcp_gateway_returns_unified_tool_specs_for_shared_servers():
    gateway = build_shared_mcp_gateway()

    specs = gateway.list_tool_specs()
    tool_names = {item["name"] for item in specs}
    server_names = {item["server_name"] for item in specs}

    assert tool_names >= {
        "crm.search_customer",
        "crm.get_customer_detail",
        "report.query",
        "report.generate",
        "approval.create_draft",
        "task.create_from_approval",
        "notify.send_task_assignment",
        "mail.send_task_assignment",
        "mail.get_delivery_status",
        "mail.list_failed_deliveries",
        "mail.retry_failed_delivery",
        "calendar.create_follow_up_event",
    }
    assert server_names >= {"crm", "report", "approval", "task", "notify", "mail", "calendar"}
    assert all(item["protocol"] == "mcp" for item in specs)


def test_mcp_gateway_can_merge_multiple_adapters_under_same_server():
    gateway = MCPGateway(
        [
            MCPServerAdapter(
                "approval",
                "Approval MCP",
                [
                    MCPToolDefinition(
                        server_name="approval",
                        tool_name="create_draft",
                        description="创建审批草稿",
                        handler=lambda context, payload: {"approval_id": "appr_001"},
                    )
                ],
            )
        ]
    )

    gateway.register_server(
        MCPServerAdapter(
            "approval",
            "Approval MCP",
            [
                MCPToolDefinition(
                    server_name="approval",
                    tool_name="create_risk_draft",
                    description="创建风险审批草稿",
                    handler=lambda context, payload: {"approval_id": "appr_002"},
                )
            ],
        )
    )

    tool_names = {item["name"] for item in gateway.list_tool_specs()}

    assert tool_names == {"approval.create_draft", "approval.create_risk_draft"}


def test_mcp_gateway_execute_returns_audit_record():
    gateway = MCPGateway(
        [
            MCPServerAdapter(
                "crm",
                "CRM MCP",
                [
                    MCPToolDefinition(
                        server_name="crm",
                        tool_name="search_customer",
                        description="搜索客户",
                        handler=lambda context, payload: {"items": [{"customer_id": payload["customer_id"]}]},
                    )
                ],
            )
        ]
    )

    result = gateway.execute("crm.search_customer", _tool_context(), {"customer_id": "cust_001"})

    assert result["protocol"] == "mcp"
    assert result["server_name"] == "crm"
    assert result["tool_name"] == "crm.search_customer"
    assert result["output"]["items"][0]["customer_id"] == "cust_001"
    assert result["audit_record"] == {
        "protocol": "mcp",
        "source": "internal",
        "server_name": "crm",
        "tool_name": "search_customer",
        "qualified_name": "crm.search_customer",
        "request_payload": {"customer_id": "cust_001"},
        "trace_summary": None,
        "tenant_id": "demo_tenant",
        "user_id": "u_demo",
        "run_id": "run_demo",
    }


def test_shared_mcp_gateway_can_execute_internal_crm_tool(monkeypatch):
    monkeypatch.setattr(
        internal_tools,
        "_load_current_user_context",
        lambda context: {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "permission_codes": ["crm:customer:read:self"],
        },
    )
    monkeypatch.setattr(
        internal_tools,
        "search_customers",
        lambda db, current_user, **kwargs: [{"customer_id": "cust_001", "keyword": kwargs.get("keyword")}],
    )

    gateway = build_shared_mcp_gateway()
    result = gateway.execute("crm.search_customer", _tool_context(), {"keyword": "华东"})

    assert result["server_name"] == "crm"
    assert result["output"]["total"] == 1
    assert result["output"]["items"][0]["customer_id"] == "cust_001"
    assert result["audit_record"]["request_payload"] == {"keyword": "华东"}


def test_shared_mcp_gateway_can_execute_mail_status_tool(monkeypatch):
    from app.modules.notification import service as notification_service

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
        "get_notification_delivery_status",
        lambda db, current_user, notification_id: {
            "notification_id": notification_id,
            "delivery_status": "fallback_internal",
            "retry_count": 1,
        },
    )

    gateway = build_shared_mcp_gateway()
    result = gateway.execute("mail.get_delivery_status", _tool_context(), {"notification_id": "notify_001"})

    assert result["server_name"] == "mail"
    assert result["tool_name"] == "mail.get_delivery_status"
    assert result["output"]["notification_id"] == "notify_001"
    assert result["output"]["delivery_status"] == "fallback_internal"
