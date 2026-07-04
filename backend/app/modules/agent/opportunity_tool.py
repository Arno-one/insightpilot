from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_opportunity_mcp_tools


def _build_reply(result: dict[str, Any]) -> str:
    lines = ["商机分析已生成。", "", "结论", f"- {result.get('summary') or '暂无商机信号。'}"]
    priority_items = list(result.get("priority_items") or [])[:5]
    if priority_items:
        lines.extend(["", "重点商机"])
        for item in priority_items:
            customer_name = item.get("customer_name") or item.get("customer_id") or "未知客户"
            deal_name = item.get("deal_name") or item.get("deal_id") or "未命名商机"
            probability = int(float(item.get("close_probability") or 0) * 100)
            alerts = "；".join(item.get("alerts") or ["暂无异常"])
            lines.append(f"- {customer_name} / {deal_name}: 成交概率 {probability}%，{alerts}")
    suggestions = [item.get("follow_up_suggestion") for item in priority_items if item.get("follow_up_suggestion")]
    if suggestions:
        lines.extend(["", "建议动作"])
        lines.extend(f"- {suggestion}" for suggestion in dict.fromkeys(suggestions))
    return "\n".join(lines)


def run_opportunity_scan_tool(
    db_rw: Session,
    current_user: dict,
    *,
    question: str,
    customer_id: str | None = None,
    owner_user_id: str | None = None,
    limit: int = 50,
    quote_timeout_days: int = 7,
) -> dict[str, Any]:
    """统一 Agent 的商机分析工具封装；V1 只生成信号和建议，不自动落地销售动作。"""
    registry = InternalToolRegistry(build_opportunity_mcp_tools())
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id="agent_chat_opportunity_scan",
        db=db_rw,
    )
    result = registry.execute(
        "opportunity.scan",
        context,
        {
            "question": question,
            "customer_id": customer_id,
            "owner_user_id": owner_user_id,
            "limit": limit,
            "quote_timeout_days": quote_timeout_days,
        },
    )["output"]
    return {
        "reply": _build_reply(result),
        "opportunity_result": result,
        "tool_name": "opportunity.scan",
        "total": result.get("total") or 0,
        "quote_timeout_count": result.get("quote_timeout_count") or 0,
        "heat_change_count": result.get("heat_change_count") or 0,
        "priority_count": len(result.get("priority_items") or []),
        "recommended_actions": list(result.get("recommended_actions") or []),
        "recommended_action_count": int(result.get("recommended_action_count") or 0),
        "error": None,
    }
