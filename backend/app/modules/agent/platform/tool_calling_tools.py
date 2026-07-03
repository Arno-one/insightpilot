from __future__ import annotations

from typing import Any

from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.calendar import service as calendar_service
from app.modules.notification import service as notification_service
from app.modules.task import service as task_service


def _require_payload_value(payload: dict[str, Any], key: str):
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"Tool Calling 工具缺少必要字段: {key}")
    return value


def build_tool_calling_internal_tools() -> list[ToolDefinition]:
    """中文注释：这批工具先把审批后的动作链闭环跑通，后续可替换为真实外部系统 adapter。"""

    def create_task_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        proposed_payload = _require_payload_value(payload, "proposed_payload")
        if not isinstance(approval, dict) or not isinstance(proposed_payload, dict):
            raise ValueError("Tool Calling 工具参数格式不正确: approval / proposed_payload")
        return task_service.create_task_from_approval(
            context.db,
            approval=approval,
            payload=proposed_payload,
            reviewer_user_id=context.user_id,
            happened_at=payload.get("happened_at"),
        )

    def send_notification_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        task = _require_payload_value(payload, "task")
        if not isinstance(approval, dict) or not isinstance(task, dict):
            raise ValueError("Tool Calling 工具参数格式不正确: approval / task")
        return notification_service.create_task_assignment_notification(
            context.db,
            tenant_id=context.tenant_id,
            approval=approval,
            task=task,
            sender_user_id=context.user_id,
            happened_at=payload.get("happened_at"),
        )

    def create_calendar_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        task = _require_payload_value(payload, "task")
        if not isinstance(approval, dict) or not isinstance(task, dict):
            raise ValueError("Tool Calling 工具参数格式不正确: approval / task")
        return calendar_service.create_follow_up_calendar_event(
            context.db,
            tenant_id=context.tenant_id,
            approval=approval,
            task=task,
            creator_user_id=context.user_id,
            happened_at=payload.get("happened_at"),
        )

    return [
        ToolDefinition(
            name="task.create_from_approval",
            description="把审批草稿转成正式销售任务，作为后续动作链的起点。",
            handler=create_task_tool,
        ),
        ToolDefinition(
            name="notify.send_task_assignment",
            description="向任务负责人发送任务通知，当前优先走邮件通道，失败时自动回退平台内通知。",
            handler=send_notification_tool,
        ),
        ToolDefinition(
            name="calendar.create_follow_up_event",
            description="为任务负责人创建平台内跟进日程，为后续真实 Calendar MCP 预留 adapter。",
            handler=create_calendar_tool,
        ),
    ]
