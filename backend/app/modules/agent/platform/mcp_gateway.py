from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from app.modules.agent.platform.data_mcp_tools import build_data_mcp_tools
from app.modules.agent.platform.internal_tools import build_shared_internal_tools
from app.modules.agent.platform.mail_mcp_tools import build_mail_mcp_tools
from app.modules.agent.platform.manager_mcp_tools import build_manager_mcp_tools
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

    def list_tool_specs(self) -> list[dict[str, str]]:
        return [
            {
                "name": tool.qualified_name,
                "description": tool.description,
                "server_name": self.server_name,
                "display_name": self.display_name,
                "protocol": tool.protocol,
                "source": tool.source,
            }
            for tool in self._tools.values()
        ]


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

    def list_tool_specs(self) -> list[dict[str, str]]:
        specs: list[dict[str, str]] = []
        for adapter in self._servers.values():
            specs.extend(adapter.list_tool_specs())
        return specs

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
        *build_data_mcp_tools(),
        *build_manager_mcp_tools(),
        *build_tool_calling_internal_tools(),
        *build_mail_mcp_tools(),
    ]
    return MCPGateway(
        [
            build_internal_mcp_server("crm", "CRM MCP", shared_tools),
            build_internal_mcp_server("report", "Report MCP", shared_tools),
            build_internal_mcp_server("approval", "Approval MCP", shared_tools),
            build_internal_mcp_server("data", "Data MCP", shared_tools),
            build_internal_mcp_server("manager", "Manager MCP", shared_tools),
            build_internal_mcp_server("task", "Task MCP", shared_tools),
            build_internal_mcp_server("notify", "Notify MCP", shared_tools),
            build_internal_mcp_server("mail", "Mail MCP", shared_tools),
            build_internal_mcp_server("calendar", "Calendar MCP", shared_tools),
        ]
    )
