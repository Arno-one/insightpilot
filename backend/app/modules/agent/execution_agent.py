from __future__ import annotations

from typing import Any


def build_approval_payload_from_action(action: dict[str, Any]) -> dict[str, Any]:
    """把经理建议动作转换为审批草稿 payload，真正执行仍等待人工审批。"""
    title = str(action.get("title") or "AI 建议执行动作")
    priority = str(action.get("priority") or "medium")
    return {
        "assignee_user_id": action.get("owner_user_id") or action.get("assignee_user_id"),
        "task_type": action.get("action_type") or "agent_follow_up",
        "title": title,
        "description": action.get("reason") or title,
        "priority": priority,
        "recommended_script": action.get("recommended_script") or action.get("reason") or "",
        "source": action.get("source") or "manager_decision",
        "deal_id": action.get("deal_id"),
        "deal_name": action.get("deal_name"),
        "requires_human_approval": True,
    }


def filter_executable_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """V1 只处理带 customer_id 且声明需审批的任务类动作。"""
    executable: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        if not action.get("customer_id"):
            continue
        if action.get("requires_approval") is False:
            continue
        executable.append(action)
    return executable


def build_execution_proposal(actions: list[dict[str, Any]], approvals: list[dict[str, Any]]) -> dict[str, Any]:
    """生成执行建议的对话摘要，明确当前只进入审批，不直接执行。"""
    return {
        "protocol": "execution.proposal.v1",
        "requested_action_count": len(actions),
        "approval_count": len(approvals),
        "approvals": approvals,
        "execution_boundary": {
            "auto_execute": False,
            "next_step": "人工审批通过后触发 post_approval_followup 动作链",
            "chain_capabilities": [
                "task.create_from_approval",
                "notify.send_task_assignment",
                "calendar.create_follow_up_event",
                "mail.send_task_assignment",
                "crm.follow_up_writeback_on_task_completion",
            ],
        },
    }
