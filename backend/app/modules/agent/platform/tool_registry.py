from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session


@dataclass(slots=True)
class ToolExecutionContext:
    """内部工具执行上下文，统一向工具暴露当前租户、用户、Run 和数据库会话。"""

    tenant_id: str
    user_id: str
    run_id: str
    db: Session
    readonly_db: Session | None = None


@dataclass(slots=True)
class ToolDefinition:
    """内部工具定义，第一阶段先覆盖平台内生能力，不直接依赖外部系统。"""

    name: str
    description: str
    handler: Callable[[ToolExecutionContext, dict[str, Any]], dict[str, Any]]


class InternalToolRegistry:
    """统一注册和执行内部工具，给后续 Planner / Executor / MCP 暴露同一层协议。"""

    def __init__(self, tools: list[ToolDefinition] | None = None):
        self._tools: dict[str, ToolDefinition] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已存在，不能重复注册: {tool.name}")
        self._tools[tool.name] = tool

    def list_tool_specs(self) -> list[dict[str, str]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self._tools.values()
        ]

    def execute(self, tool_name: str, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"未注册的内部工具: {tool_name}")
        output = tool.handler(context, payload)
        return {
            "tool_name": tool.name,
            "description": tool.description,
            "output": output,
        }
