from __future__ import annotations

from typing import Any

from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.notification import service as notification_service


def _require_payload_value(payload: dict[str, Any], key: str):
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"Mail MCP 工具缺少必要字段: {key}")
    return value


def build_mail_mcp_tools() -> list[ToolDefinition]:
    """中文注释：Mail MCP V1 先覆盖发送、状态查询和失败重试，后续再接真实外部 Mail Gateway。"""

    def send_task_assignment_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        task = _require_payload_value(payload, "task")
        if not isinstance(approval, dict) or not isinstance(task, dict):
            raise ValueError("Mail MCP 工具参数格式不正确: approval / task")
        return notification_service.create_task_assignment_notification(
            context.db,
            tenant_id=context.tenant_id,
            approval=approval,
            task=task,
            sender_user_id=context.user_id,
            happened_at=payload.get("happened_at"),
        )

    def get_delivery_status_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = notification_service.load_notification_operator_context(
            context.db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        notification_id = str(_require_payload_value(payload, "notification_id"))
        return notification_service.get_notification_delivery_status(
            context.db,
            current_user=current_user,
            notification_id=notification_id,
        )

    def list_failed_deliveries_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = notification_service.load_notification_operator_context(
            context.db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        items = notification_service.list_failed_notification_deliveries(
            context.db,
            current_user=current_user,
            limit=int(payload.get("limit", 20)),
        )
        return {
            "items": items,
            "total": len(items),
        }

    def retry_failed_delivery_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = notification_service.load_notification_operator_context(
            context.db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        notification_id = str(_require_payload_value(payload, "notification_id"))
        return notification_service.retry_notification_delivery(
            context.db,
            current_user=current_user,
            notification_id=notification_id,
            happened_at=payload.get("happened_at"),
        )

    return [
        ToolDefinition(
            name="mail.send_task_assignment",
            description="通过 Mail MCP 发送任务通知，失败时由通知服务自动回退平台内通知。",
            handler=send_task_assignment_tool,
        ),
        ToolDefinition(
            name="mail.get_delivery_status",
            description="查询单条通知的邮件投递状态、重试次数和最后错误。",
            handler=get_delivery_status_tool,
        ),
        ToolDefinition(
            name="mail.list_failed_deliveries",
            description="列出邮件投递失败或回退的平台通知，便于人工或 Agent 做补发处理。",
            handler=list_failed_deliveries_tool,
        ),
        ToolDefinition(
            name="mail.retry_failed_delivery",
            description="对失败或回退的通知执行邮件补发，并回写最新投递状态。",
            handler=retry_failed_delivery_tool,
        ),
    ]
