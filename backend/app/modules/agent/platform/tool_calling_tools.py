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


def _preview_text(value: Any, fallback: str) -> str:
    """中文注释：预留工具只做展示型 mock，所有标题字段都收敛为安全字符串。"""
    text = str(value or "").strip()
    return text or fallback


def build_tool_calling_internal_tools() -> list[ToolDefinition]:
    """中文注释：这批工具先把审批后的动作链闭环跑通，后续可替换为真实外部系统 adapter。"""

    def preview_task_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        proposed_payload = _require_payload_value(payload, "proposed_payload")
        if not isinstance(approval, dict) or not isinstance(proposed_payload, dict):
            raise ValueError("Task MCP 预览工具参数格式不正确: approval / proposed_payload")
        title = _preview_text(
            proposed_payload.get("title") or proposed_payload.get("task_title") or proposed_payload.get("action"),
            "AI 建议跟进任务",
        )
        task_preview = {
            "title": title,
            "priority": proposed_payload.get("priority") or approval.get("priority") or "medium",
            "customer_id": proposed_payload.get("customer_id") or approval.get("customer_id"),
            "assignee_user_id": proposed_payload.get("assignee_user_id") or approval.get("owner_user_id"),
            "source_approval_id": approval.get("approval_id"),
            "dry_run": True,
        }
        return {
            "protocol": "task.preview_from_approval.v1",
            "task_preview": task_preview,
            "trace": {
                "protocol": "task.preview_from_approval.v1",
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "tool_name": "task.preview_from_approval",
                "approval_id": approval.get("approval_id"),
                "dry_run": True,
                "external_system": "not_connected",
            },
        }

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

    def preview_calendar_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        approval = _require_payload_value(payload, "approval")
        task = _require_payload_value(payload, "task")
        if not isinstance(approval, dict) or not isinstance(task, dict):
            raise ValueError("Calendar MCP 预览工具参数格式不正确: approval / task")
        title = _preview_text(task.get("title") or task.get("task_title"), "客户跟进日程")
        calendar_preview = {
            "event_title": f"跟进任务：{title}",
            "task_id": task.get("task_id"),
            "customer_id": task.get("customer_id") or approval.get("customer_id"),
            "assignee_user_id": task.get("assignee_user_id"),
            "start_time_hint": payload.get("start_time") or task.get("due_at") or "next_available_slot",
            "duration_minutes": int(payload.get("duration_minutes") or 30),
            "dry_run": True,
        }
        return {
            "protocol": "calendar.preview_follow_up_event.v1",
            "calendar_preview": calendar_preview,
            "trace": {
                "protocol": "calendar.preview_follow_up_event.v1",
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "tool_name": "calendar.preview_follow_up_event",
                "approval_id": approval.get("approval_id"),
                "task_id": task.get("task_id"),
                "dry_run": True,
                "external_system": "not_connected",
            },
        }

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
            name="task.preview_from_approval",
            description="基于审批草稿生成任务预览，不写入数据库，用于 Task MCP 外部适配前的 dry-run 协议预留。",
            handler=preview_task_tool,
        ),
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
            name="calendar.preview_follow_up_event",
            description="生成跟进日程预览，不连接外部日历，用于 Calendar MCP 外部适配前的 dry-run 协议预留。",
            handler=preview_calendar_tool,
        ),
        ToolDefinition(
            name="calendar.create_follow_up_event",
            description="为任务负责人创建平台内跟进日程，为后续真实 Calendar MCP 预留 adapter。",
            handler=create_calendar_tool,
        ),
    ]
