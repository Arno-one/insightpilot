from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent.platform.mcp_gateway import build_shared_mcp_gateway
from app.modules.agent.platform.tool_registry import ToolExecutionContext


POST_APPROVAL_TOOL_CHAIN: tuple[tuple[str, str], ...] = (
    ("task.create_from_approval", "审批通过后先生成正式任务，确保后续动作有稳定的业务主键。"),
    ("notify.send_task_assignment", "任务生成后立即通知负责人，避免 AI 建议停留在系统内无人认领。"),
    ("calendar.create_follow_up_event", "通知后同步创建跟进日程，占住执行时间窗口。"),
)


def execute_post_approval_action_flow(
    db: Session,
    *,
    current_user: dict[str, Any],
    approval: dict[str, Any],
    proposed_payload: dict[str, Any],
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：审批通过后的动作链统一收敛到这里，后续接外部系统时只需要替换具体 adapter。"""

    gateway = build_shared_mcp_gateway()
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id=approval.get("run_id") or f"approval_{approval['approval_id']}",
        db=db,
    )
    runtime_payload: dict[str, Any] = {
        "approval": approval,
        "proposed_payload": proposed_payload,
        "happened_at": happened_at,
    }
    execution_records: list[dict[str, Any]] = []

    for tool_name, reason in POST_APPROVAL_TOOL_CHAIN:
        execution = gateway.execute(tool_name, context, runtime_payload)
        execution_records.append(
            {
                "tool_name": execution["tool_name"],
                "server_name": execution["server_name"],
                "protocol": execution["protocol"],
                "reason": reason,
                "audit_record": execution["audit_record"],
                "output": execution["output"],
            }
        )
        if tool_name == "task.create_from_approval":
            runtime_payload["task"] = execution["output"]
        elif tool_name == "notify.send_task_assignment":
            runtime_payload["notification"] = execution["output"]
        elif tool_name == "calendar.create_follow_up_event":
            runtime_payload["calendar_event"] = execution["output"]

    task = runtime_payload.get("task", {})
    notification = runtime_payload.get("notification", {})
    calendar_event = runtime_payload.get("calendar_event", {})
    return {
        "task_id": task.get("task_id"),
        "task": task,
        "notification": notification,
        "calendar_event": calendar_event,
        "tool_executions": execution_records,
    }
