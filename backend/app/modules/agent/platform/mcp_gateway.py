from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from app.modules.agent.platform.customer_profile_mcp_tools import build_customer_profile_mcp_tools
from app.modules.agent.platform.data_mcp_tools import build_data_mcp_tools
from app.modules.agent.platform.execution_mcp_tools import build_execution_mcp_tools
from app.modules.agent.platform.followup_strategy_mcp_tools import build_followup_strategy_mcp_tools
from app.modules.agent.platform.internal_tools import build_shared_internal_tools
from app.modules.agent.platform.mail_mcp_tools import build_mail_mcp_tools
from app.modules.agent.platform.manager_mcp_tools import build_manager_mcp_tools
from app.modules.agent.platform.opportunity_mcp_tools import build_opportunity_mcp_tools
from app.modules.agent.platform.tool_calling_tools import build_tool_calling_internal_tools
from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext


@dataclass(slots=True)
class MCPToolDefinition:
    """中文注释：统一描述一个 MCP 工具，先承接平台内生工具，后续再接外部系统。"""

    server_name: str
    tool_name: str
    description: str
    handler: Callable[[ToolExecutionContext, dict[str, Any]], dict[str, Any]]
    source: str = "internal"
    protocol: str = "mcp"

    @property
    def qualified_name(self) -> str:
        return f"{self.server_name}.{self.tool_name}"

    def to_registry_entry(self, display_name: str, current_user: dict[str, Any] | None = None) -> dict[str, Any]:
        """中文注释：把工具定义转换为注册表条目，供前端和后续治理能力只读消费。"""
        scope = self.server_name
        policy = _build_tool_permission_policy(self.qualified_name, self.server_name, self.tool_name)
        permissions = set((current_user or {}).get("permission_codes") or [])
        missing_permissions = [
            permission for permission in policy["required_permissions"] if permission not in permissions
        ]
        return {
            "name": self.qualified_name,
            "tool_name": self.tool_name,
            "description": self.description,
            "server_name": self.server_name,
            "display_name": display_name,
            "protocol": self.protocol,
            "source": self.source,
            "scope": scope,
            "scopes": [scope],
            **policy,
            "available": current_user is None or not missing_permissions,
            "missing_permissions": missing_permissions if current_user is not None else [],
        }


def _build_tool_permission_policy(qualified_name: str, server_name: str, tool_name: str) -> dict[str, Any]:
    """中文注释：MCP Tool Permission V1 先用稳定规则补齐权限、风险和副作用标签。"""
    exact_permissions = {
        "report.query": ["report:read:team"],
        "report.generate": ["agent:run:business_report"],
        "task.create_from_approval": ["approval:review:agent_task"],
        "notify.send_task_assignment": ["approval:review:agent_task"],
        "mail.send_task_assignment": ["approval:review:agent_task"],
        "mail.get_delivery_status": ["task:read:team"],
        "mail.list_failed_deliveries": ["task:read:team"],
        "mail.retry_failed_delivery": ["task:read:team"],
        "calendar.create_follow_up_event": ["approval:review:agent_task"],
    }
    server_permissions = {
        "crm": ["crm:customer:read:self"],
        "profile": ["crm:customer:read:self"],
        "approval": ["crm:customer:read:self"],
        "data": ["crm:customer:read:self"],
        "execution": ["crm:customer:read:self"],
        "followup": ["crm:customer:read:self"],
        "manager": ["crm:customer:read:self"],
        "opportunity": ["crm:customer:read:self"],
    }
    side_effect_names = {
        "approval.create_draft",
        "execution.propose_actions",
        "report.generate",
        "task.create_from_approval",
        "notify.send_task_assignment",
        "mail.send_task_assignment",
        "mail.retry_failed_delivery",
        "calendar.create_follow_up_event",
    }
    approval_required_names = {
        "approval.create_draft",
        "execution.propose_actions",
        "task.create_from_approval",
        "notify.send_task_assignment",
        "mail.send_task_assignment",
        "mail.retry_failed_delivery",
        "calendar.create_follow_up_event",
    }
    high_risk_names = {
        "approval.create_draft",
        "execution.propose_actions",
        "task.create_from_approval",
        "notify.send_task_assignment",
        "mail.send_task_assignment",
        "mail.retry_failed_delivery",
        "calendar.create_follow_up_event",
    }
    medium_risk_servers = {"data", "report", "manager", "opportunity"}

    required_permissions = exact_permissions.get(qualified_name, server_permissions.get(server_name, []))
    if qualified_name in high_risk_names:
        risk_level = "high"
    elif server_name in medium_risk_servers or tool_name.startswith(("query", "analyze", "generate")):
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "permission_policy_version": "mcp_tool_permission_v1",
        "required_permissions": required_permissions,
        "risk_level": risk_level,
        "approval_required": qualified_name in approval_required_names,
        "side_effect": qualified_name in side_effect_names,
        "governance_tags": [
            tag
            for tag, enabled in {
                "requires_permission": bool(required_permissions),
                "requires_approval": qualified_name in approval_required_names,
                "has_side_effect": qualified_name in side_effect_names,
                "read_only": qualified_name not in side_effect_names,
            }.items()
            if enabled
        ],
    }


class MCPServerAdapter:
    """中文注释：一个 Adapter 代表一个 MCP Server，下挂多个工具。"""

    def __init__(
        self,
        server_name: str,
        display_name: str,
        tools: list[MCPToolDefinition] | None = None,
        *,
        protocol: str = "mcp",
    ):
        self.server_name = server_name
        self.display_name = display_name
        self.protocol = protocol
        self._tools: dict[str, MCPToolDefinition] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: MCPToolDefinition) -> None:
        if tool.server_name != self.server_name:
            raise ValueError(f"MCP 工具与 Server 不匹配: {tool.qualified_name} -> {self.server_name}")
        if tool.qualified_name in self._tools:
            raise ValueError(f"MCP 工具已存在，不能重复注册: {tool.qualified_name}")
        self._tools[tool.qualified_name] = tool

    def get_tool(self, qualified_name: str) -> MCPToolDefinition | None:
        return self._tools.get(qualified_name)

    def list_tool_specs(self, current_user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [
            tool.to_registry_entry(self.display_name, current_user)
            for tool in self._tools.values()
        ]

    def to_registry_entry(self, current_user: dict[str, Any] | None = None) -> dict[str, Any]:
        """中文注释：聚合单个 MCP Server 的注册信息，V1 只暴露只读元数据。"""
        tools = self.list_tool_specs(current_user)
        scopes = sorted({scope for tool in tools for scope in tool.get("scopes", [])})
        sources = sorted({tool["source"] for tool in tools})
        risk_order = {"low": 1, "medium": 2, "high": 3}
        max_risk_level = max(
            (tool["risk_level"] for tool in tools),
            key=lambda risk_level: risk_order.get(risk_level, 0),
            default="low",
        )
        return {
            "server_name": self.server_name,
            "display_name": self.display_name,
            "protocol": self.protocol,
            "source": sources[0] if len(sources) == 1 else ("mixed" if sources else "unknown"),
            "sources": sources,
            "scope": self.server_name,
            "scopes": scopes or [self.server_name],
            "tool_count": len(tools),
            "available_tool_count": sum(1 for tool in tools if tool["available"]),
            "max_risk_level": max_risk_level,
            "approval_required_tool_count": sum(1 for tool in tools if tool["approval_required"]),
            "side_effect_tool_count": sum(1 for tool in tools if tool["side_effect"]),
            "tools": tools,
        }


class MCPGateway:
    """中文注释：给 Planner / Executor 暴露统一 MCP 协议，底层可以接内部工具或外部工具。"""

    def __init__(self, adapters: list[MCPServerAdapter] | None = None):
        self._servers: dict[str, MCPServerAdapter] = {}
        for adapter in adapters or []:
            self.register_server(adapter)

    def register_server(self, adapter: MCPServerAdapter) -> None:
        existing = self._servers.get(adapter.server_name)
        if not existing:
            self._servers[adapter.server_name] = adapter
            return
        for spec in adapter.list_tool_specs():
            tool = adapter.get_tool(spec["name"])
            if tool:
                existing.register(tool)

    def list_tool_specs(self, current_user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for adapter in self._servers.values():
            specs.extend(adapter.list_tool_specs(current_user))
        return specs

    def list_server_registry(self, current_user: dict[str, Any] | None = None) -> dict[str, Any]:
        """中文注释：输出统一 MCP Gateway 注册表，为权限、审计和健康检查打基础。"""
        servers = [adapter.to_registry_entry(current_user) for adapter in self._servers.values()]
        tools = [tool for server in servers for tool in server["tools"]]
        scope_summary: dict[str, dict[str, Any]] = {}
        for tool in tools:
            for scope in tool.get("scopes", []):
                item = scope_summary.setdefault(scope, {"scope": scope, "server_count": 0, "tool_count": 0})
                item["tool_count"] += 1
        for scope, item in scope_summary.items():
            item["server_count"] = sum(1 for server in servers if scope in server.get("scopes", []))

        return {
            "registry_version": "mcp_gateway_registry_v1",
            "permission_policy_version": "mcp_tool_permission_v1",
            "server_count": len(servers),
            "tool_count": len(tools),
            "available_tool_count": sum(1 for tool in tools if tool["available"]),
            "high_risk_tool_count": sum(1 for tool in tools if tool["risk_level"] == "high"),
            "approval_required_tool_count": sum(1 for tool in tools if tool["approval_required"]),
            "side_effect_tool_count": sum(1 for tool in tools if tool["side_effect"]),
            "scope_count": len(scope_summary),
            "servers": servers,
            "tools": tools,
            "scope_summary": sorted(scope_summary.values(), key=lambda item: item["scope"]),
        }

    def execute(self, qualified_name: str, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        server_name, _, _ = qualified_name.partition(".")
        adapter = self._servers.get(server_name)
        tool = adapter.get_tool(qualified_name) if adapter else None
        if not tool:
            raise ValueError(f"未注册的 MCP 工具: {qualified_name}")
        request_payload = _to_json_safe(copy.deepcopy(payload))
        output = tool.handler(context, payload)
        trace_summary = output.get("trace") if isinstance(output, dict) else None
        return {
            "protocol": tool.protocol,
            "server_name": tool.server_name,
            "tool_name": tool.qualified_name,
            "description": tool.description,
            "output": output,
            "audit_record": {
                "protocol": tool.protocol,
                "source": tool.source,
                "server_name": tool.server_name,
                "tool_name": tool.tool_name,
                "qualified_name": tool.qualified_name,
                "request_payload": request_payload,
                "trace_summary": _to_json_safe(trace_summary) if trace_summary else None,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "run_id": context.run_id,
            },
        }


def _to_json_safe(value: Any) -> Any:
    """中文注释：Tool Calling 审计记录后续要进 Trace 和 JSON 字段，这里统一转成可序列化结构。"""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_safe(item) for item in value]
    return value


def _tool_name_without_server(tool_name: str, server_name: str) -> str:
    prefix = f"{server_name}."
    if not tool_name.startswith(prefix):
        raise ValueError(f"内部工具无法映射到 MCP Server: {tool_name} -> {server_name}")
    return tool_name[len(prefix) :]


def build_internal_mcp_server(server_name: str, display_name: str, tools: list[ToolDefinition]) -> MCPServerAdapter:
    """中文注释：把现有内部工具包装成一个 MCP Server Adapter。"""

    adapter_tools = [
        MCPToolDefinition(
            server_name=server_name,
            tool_name=_tool_name_without_server(tool.name, server_name),
            description=tool.description,
            handler=tool.handler,
            source="internal",
        )
        for tool in tools
        if tool.name.startswith(f"{server_name}.")
    ]
    return MCPServerAdapter(server_name, display_name, adapter_tools)


def build_shared_mcp_gateway() -> MCPGateway:
    """中文注释：把当前平台内生能力统一接成 MCP Gateway，共享给 Agent 和审批后的动作链。"""

    shared_tools = [
        *build_shared_internal_tools(),
        *build_customer_profile_mcp_tools(),
        *build_data_mcp_tools(),
        *build_execution_mcp_tools(),
        *build_followup_strategy_mcp_tools(),
        *build_manager_mcp_tools(),
        *build_tool_calling_internal_tools(),
        *build_mail_mcp_tools(),
        *build_opportunity_mcp_tools(),
    ]
    return MCPGateway(
        [
            build_internal_mcp_server("crm", "CRM MCP", shared_tools),
            build_internal_mcp_server("profile", "Customer Profile MCP", shared_tools),
            build_internal_mcp_server("report", "Report MCP", shared_tools),
            build_internal_mcp_server("approval", "Approval MCP", shared_tools),
            build_internal_mcp_server("data", "Data MCP", shared_tools),
            build_internal_mcp_server("execution", "Execution MCP", shared_tools),
            build_internal_mcp_server("followup", "Follow-up Strategy MCP", shared_tools),
            build_internal_mcp_server("manager", "Manager MCP", shared_tools),
            build_internal_mcp_server("task", "Task MCP", shared_tools),
            build_internal_mcp_server("notify", "Notify MCP", shared_tools),
            build_internal_mcp_server("mail", "Mail MCP", shared_tools),
            build_internal_mcp_server("opportunity", "Opportunity MCP", shared_tools),
            build_internal_mcp_server("calendar", "Calendar MCP", shared_tools),
        ]
    )
