from __future__ import annotations

from typing import Any

from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.notification import service as notification_service


def _require_payload_value(payload: dict[str, Any], key: str):
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"Mail MCP 工具缺少必要字段: {key}")
    return value


def _compact_approval_context(approval: dict[str, Any]) -> dict[str, Any]:
    """中文注释：Trace 只记录审批关键字段，避免把完整业务载荷塞进审计摘要。"""
    return {
        "approval_id": approval.get("approval_id"),
        "approval_type": approval.get("approval_type"),
        "approval_status": approval.get("status"),
        "customer_id": approval.get("customer_id"),
        "run_id": approval.get("run_id"),
    }


def _compact_task_context(task: dict[str, Any]) -> dict[str, Any]:
    """中文注释：任务上下文同样只保留主键和负责人，方便 Trace 串起动作链。"""
    return {
        "task_id": task.get("task_id"),
        "assignee_user_id": task.get("assignee_user_id"),
        "customer_id": task.get("customer_id"),
    }


def _with_mail_trace(
    *,
    context: ToolExecutionContext,
    tool_name: str,
    output: dict[str, Any],
    approval: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """中文注释：统一给 Mail MCP 输出补 Trace 摘要，供 MCP Gateway 审计直接落库。"""
    trace = {
        "protocol": f"{tool_name}.v1",
        "run_id": context.run_id,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "tool_name": tool_name,
        "notification_id": output.get("notification_id"),
        "delivery_status": output.get("delivery_status"),
        "retry_count": output.get("retry_count"),
        "approval": _compact_approval_context(approval) if approval else None,
        "task": _compact_task_context(task) if task else None,
    }
    return {
        **output,
        "protocol": f"{tool_name}.v1",
        "trace": trace,
    }


def build_mail_mcp_tools() -> list[ToolDefinition]:
    """中文注释：Mail MCP V1 先覆盖发送、状态查询和失败重试，后续再接真实外部 Mail Gateway。"""

    def send_task_assignment_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        task = _require_payload_value(payload, "task")
        if not isinstance(approval, dict) or not isinstance(task, dict):
            raise ValueError("Mail MCP 工具参数格式不正确: approval / task")
        output = notification_service.create_task_assignment_notification(
            context.db,
            tenant_id=context.tenant_id,
            approval=approval,
            task=task,
            sender_user_id=context.user_id,
            happened_at=payload.get("happened_at"),
        )
        return _with_mail_trace(
            context=context,
            tool_name="mail.send_task_assignment",
            output=output,
            approval=approval,
            task=task,
        )

    def get_delivery_status_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = notification_service.load_notification_operator_context(
            context.db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        notification_id = str(_require_payload_value(payload, "notification_id"))
        output = notification_service.get_notification_delivery_status(
            context.db,
            current_user=current_user,
            notification_id=notification_id,
        )
        return _with_mail_trace(
            context=context,
            tool_name="mail.get_delivery_status",
            output=output,
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
            "protocol": "mail.list_failed_deliveries.v1",
            "items": items,
            "total": len(items),
            "trace": {
                "protocol": "mail.list_failed_deliveries.v1",
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "tool_name": "mail.list_failed_deliveries",
                "item_count": len(items),
            },
        }

    def retry_failed_delivery_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = notification_service.load_notification_operator_context(
            context.db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )
        notification_id = str(_require_payload_value(payload, "notification_id"))
        output = notification_service.retry_notification_delivery(
            context.db,
            current_user=current_user,
            notification_id=notification_id,
            happened_at=payload.get("happened_at"),
        )
        return _with_mail_trace(
            context=context,
            tool_name="mail.retry_failed_delivery",
            output=output,
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
