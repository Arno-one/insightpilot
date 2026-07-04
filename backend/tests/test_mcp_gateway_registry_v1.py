from fastapi.testclient import TestClient

from app.main import app
from app.modules.agent.platform import MCPGateway, MCPServerAdapter, build_shared_mcp_gateway
from tests.test_agent_chat_api_v1 import _build_headers


def test_mcp_gateway_registry_groups_servers_tools_and_scopes():
    gateway = build_shared_mcp_gateway()

    registry = gateway.list_server_registry()
    servers_by_name = {item["server_name"]: item for item in registry["servers"]}
    tools_by_name = {item["name"]: item for item in registry["tools"]}

    assert registry["registry_version"] == "mcp_gateway_registry_v1"
    assert registry["server_count"] == len(registry["servers"])
    assert registry["tool_count"] == len(registry["tools"])
    assert registry["scope_count"] == len(registry["scope_summary"])

    assert {"data", "mail", "crm", "execution"}.issubset(servers_by_name)
    assert servers_by_name["data"]["tool_count"] == len(servers_by_name["data"]["tools"])
    assert servers_by_name["mail"]["tool_count"] == len(servers_by_name["mail"]["tools"])
    assert servers_by_name["data"]["scopes"] == ["data"]
    assert servers_by_name["mail"]["scopes"] == ["mail"]

    assert "data.query_sql" in tools_by_name
    assert "mail.get_delivery_status" in tools_by_name
    assert tools_by_name["data.query_sql"]["scope"] == "data"
    assert tools_by_name["mail.get_delivery_status"]["server_name"] == "mail"
    assert all(tool["protocol"] == "mcp" for tool in registry["tools"])
    assert all(tool["source"] == "internal" for tool in registry["tools"])


def test_mcp_gateway_registry_allows_empty_placeholder_server():
    gateway = MCPGateway([MCPServerAdapter("external_pending", "External Pending MCP")])

    registry = gateway.list_server_registry()
    server = registry["servers"][0]

    assert registry["server_count"] == 1
    assert registry["tool_count"] == 0
    assert server["source"] == "unknown"
    assert server["tool_count"] == 0
    assert server["scopes"] == ["external_pending"]


def test_mcp_gateway_registry_api_returns_readonly_registry():
    client = TestClient(app)
    headers, _, _ = _build_headers(client)

    response = client.get("/api/agent/mcp/registry", headers=headers)

    assert response.status_code == 200
    body = response.json()
    data = body["data"]

    assert body["total"] == data["server_count"]
    assert data["registry_version"] == "mcp_gateway_registry_v1"
    assert data["server_count"] >= 10
    assert data["tool_count"] == len(data["tools"])
    assert {server["server_name"] for server in data["servers"]} >= {"data", "mail", "crm"}
