from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent.platform import build_shared_mcp_gateway
from tests.test_agent_chat_api_v1 import _build_headers


def test_mcp_tool_permission_policy_exposes_required_permissions_and_risk():
    registry = build_shared_mcp_gateway().list_server_registry()
    tools_by_name = {tool["name"]: tool for tool in registry["tools"]}

    assert registry["permission_policy_version"] == "mcp_tool_permission_v1"
    assert registry["high_risk_tool_count"] > 0
    assert registry["side_effect_tool_count"] > 0
    assert registry["approval_required_tool_count"] > 0

    data_query = tools_by_name["data.query_sql"]
    assert data_query["required_permissions"] == ["crm:customer:read:self"]
    assert data_query["risk_level"] == "medium"
    assert data_query["side_effect"] is False
    assert data_query["approval_required"] is False
    assert "read_only" in data_query["governance_tags"]

    mail_retry = tools_by_name["mail.retry_failed_delivery"]
    assert mail_retry["required_permissions"] == ["task:read:team"]
    assert mail_retry["risk_level"] == "high"
    assert mail_retry["side_effect"] is True
    assert mail_retry["approval_required"] is True
    assert {"requires_permission", "requires_approval", "has_side_effect"}.issubset(mail_retry["governance_tags"])


def test_mcp_tool_permission_policy_marks_current_user_availability():
    current_user = {
        "tenant_id": "demo_tenant",
        "user_id": "u_demo",
        "permission_codes": ["crm:customer:read:self"],
    }

    registry = build_shared_mcp_gateway().list_server_registry(current_user)
    tools_by_name = {tool["name"]: tool for tool in registry["tools"]}

    assert tools_by_name["data.query_sql"]["available"] is True
    assert tools_by_name["data.query_sql"]["missing_permissions"] == []
    assert tools_by_name["mail.get_delivery_status"]["available"] is False
    assert tools_by_name["mail.get_delivery_status"]["missing_permissions"] == ["task:read:team"]
    assert registry["available_tool_count"] < registry["tool_count"]


def test_mcp_registry_api_returns_permission_policy_for_current_user():
    client = TestClient(app)
    headers, _, _ = _build_headers(client)

    response = client.get("/api/agent/mcp/registry", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    tools_by_name = {tool["name"]: tool for tool in data["tools"]}

    assert data["permission_policy_version"] == "mcp_tool_permission_v1"
    assert data["available_tool_count"] <= data["tool_count"]
    assert tools_by_name["data.query_sql"]["available"] is True
    assert "required_permissions" in tools_by_name["approval.create_draft"]
    assert "risk_level" in tools_by_name["approval.create_draft"]
