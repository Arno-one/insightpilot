from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent import intent_router
from app.modules.agent.platform import execute_agent_chat_tool


def _build_reply(result: dict[str, Any]) -> str:
    lines = ["跟进策略已生成。", "", "结论", f"- {result.get('summary') or '暂无明确策略。'}"]
    talking_points = list(result.get("talking_points") or [])
    if talking_points:
        lines.extend(["", "沟通重点"])
        lines.extend(f"- {point}" for point in talking_points[:5])
    actions = list(result.get("recommended_actions") or [])
    if actions:
        lines.extend(["", "建议动作"])
        for action in actions[:3]:
            lines.append(f"- [{action.get('priority') or 'medium'}] {action.get('title') or '创建跟进任务'}，需审批")
    return "\n".join(lines)


def run_followup_strategy_tool(
    db_rw: Session,
    current_user: dict,
    *,
    customer_id: str,
    question: str,
) -> dict[str, Any]:
    """统一 Agent 的跟进策略工具封装；只输出策略和审批动作，不直接创建任务。"""
    routed_result = execute_agent_chat_tool(
        db_rw=db_rw,
        db_readonly=None,
        current_user=current_user,
        run_id="agent_chat_followup_strategy",
        intent=intent_router.INTENT_FOLLOW_UP_STRATEGY,
        agent_scope="customer",
        payload={"customer_id": customer_id, "question": question},
        has_related_customer=True,
        preferred_tool="followup.plan_strategy",
    )
    result = routed_result["output"]
    return {
        "reply": _build_reply(result),
        "strategy_result": result,
        "tool_name": "followup.plan_strategy",
        "tool_route": routed_result["route"],
        "customer_id": customer_id,
        "strategy_level": result.get("strategy_level"),
        "recommended_actions": list(result.get("recommended_actions") or []),
        "recommended_action_count": int(result.get("recommended_action_count") or 0),
        "error": None,
    }
