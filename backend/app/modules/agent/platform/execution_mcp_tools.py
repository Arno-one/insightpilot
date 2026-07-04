from __future__ import annotations

from typing import Any

from app.modules.agent.execution_agent import (
    build_approval_payload_from_action,
    build_execution_proposal,
    filter_executable_actions,
)
from app.modules.agent.platform.internal_tools import _load_current_user_context, _require_permission, build_shared_internal_tools
from app.modules.agent.platform.tool_registry import InternalToolRegistry, ToolDefinition, ToolExecutionContext


def build_execution_mcp_tools() -> list[ToolDefinition]:
    """注册 Execution Agent V2 工具：只提交审批草稿，不绕过人工审批执行。"""

    def propose_actions_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        raw_actions = payload.get("actions")
        actions = filter_executable_actions(raw_actions if isinstance(raw_actions, list) else [])
        registry = InternalToolRegistry(build_shared_internal_tools())

        approvals: list[dict[str, Any]] = []
        for action in actions:
            approval = registry.execute(
                "approval.create_draft",
                context,
                {
                    "customer_id": action["customer_id"],
                    "risk_snapshot_id": action.get("risk_snapshot_id"),
                    "approval_type": "agent_execution_draft",
                    "proposed_payload": build_approval_payload_from_action(action),
                    "note": "AI 执行建议已进入人工审批队列，审批通过后才会触发动作链",
                },
            )["output"]
            approvals.append(approval)

        proposal = build_execution_proposal(actions, approvals)
        return {
            "protocol": "execution.propose_actions.v1",
            "proposal": proposal,
            "trace": {
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "requested_action_count": len(raw_actions) if isinstance(raw_actions, list) else 0,
                "executable_action_count": len(actions),
                "approval_count": len(approvals),
            },
        }

    return [
        ToolDefinition(
            name="execution.propose_actions",
            description="把对话内建议动作转换为人工审批草稿，审批通过后再触发任务、通知、日程、邮件等动作链。",
            handler=propose_actions_tool,
        )
    ]
