from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _coerce_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _days_since(value: Any, now: datetime) -> int | None:
    target = _coerce_datetime(value)
    if not target:
        return None
    return max(0, (now - target).days)


def _latest_open_deal(deals: list[dict[str, Any]]) -> dict[str, Any]:
    for deal in deals:
        if str(deal.get("close_result") or "open") == "open":
            return deal
    return deals[0] if deals else {}


def _latest_risk(risks: list[dict[str, Any]]) -> dict[str, Any]:
    return risks[0] if risks else {}


def _strategy_level(customer: dict[str, Any], risk: dict[str, Any], last_follow_days: int | None) -> str:
    risk_score = int(risk.get("risk_score") or 0)
    if risk_score >= 80 or customer.get("competitor_involved") or (last_follow_days is not None and last_follow_days >= 21):
        return "rescue"
    if str(customer.get("intent_level") or "").lower() == "high" or risk_score >= 60:
        return "accelerate"
    if last_follow_days is None or last_follow_days >= 14:
        return "reactivate"
    return "nurture"


def _cadence_for_level(level: str) -> dict[str, Any]:
    cadences = {
        "rescue": {"priority": "high", "next_touch_days": 1, "channel": "phone", "label": "抢救式跟进"},
        "accelerate": {"priority": "high", "next_touch_days": 2, "channel": "meeting", "label": "加速推进"},
        "reactivate": {"priority": "medium", "next_touch_days": 3, "channel": "wechat", "label": "唤醒跟进"},
        "nurture": {"priority": "low", "next_touch_days": 7, "channel": "wechat", "label": "持续培育"},
    }
    return cadences[level]


def _build_talking_points(customer: dict[str, Any], deal: dict[str, Any], risk: dict[str, Any], memory: dict[str, Any]) -> list[str]:
    points: list[str] = []
    if deal.get("deal_name"):
        points.append(f"围绕商机《{deal['deal_name']}》确认下一步决策时间。")
    if deal.get("quote_amount"):
        points.append("核对报价反馈、预算口径和竞品对比点。")
    if customer.get("competitor_involved"):
        points.append("主动询问竞品推进情况，确认客户真实顾虑。")
    if risk.get("llm_suggestion"):
        points.append(str(risk["llm_suggestion"]))
    if memory.get("summary_text"):
        points.append(f"结合客户画像摘要：{str(memory['summary_text'])[:120]}")
    if not points:
        points.append("先确认客户当前业务优先级，再约定下一次明确跟进时间。")
    return points[:5]


def build_followup_strategy(
    customer_detail: dict[str, Any],
    *,
    customer_memory: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """基于客户全貌生成跟进策略；V1 只生成建议动作，真正落地交给审批链。"""
    now = now or datetime.now()
    customer = customer_detail.get("customer") or {}
    deals = list(customer_detail.get("deals") or [])
    follow_ups = list(customer_detail.get("follow_ups") or [])
    risks = list(customer_detail.get("risk_snapshots") or [])
    tasks = list(customer_detail.get("tasks") or [])
    approvals = list(customer_detail.get("approvals") or [])
    memory = customer_memory or {}

    latest_follow = follow_ups[0] if follow_ups else {}
    last_follow_at = latest_follow.get("occurred_at") or customer.get("last_follow_up_at")
    last_follow_days = _days_since(last_follow_at, now)
    deal = _latest_open_deal(deals)
    risk = _latest_risk(risks)
    level = _strategy_level(customer, risk, last_follow_days)
    cadence = _cadence_for_level(level)
    active_task_count = len([task for task in tasks if task.get("status") in {"pending", "in_progress"}])
    pending_approval_count = len([item for item in approvals if item.get("status") == "pending"])
    talking_points = _build_talking_points(customer, deal, risk, memory)

    customer_id = customer.get("customer_id")
    customer_name = customer.get("customer_name") or customer_id
    action = {
        "action_type": "create_follow_up_task",
        "source": "follow_up_strategy",
        "priority": cadence["priority"],
        "customer_id": customer_id,
        "customer_name": customer_name,
        "deal_id": deal.get("deal_id"),
        "deal_name": deal.get("deal_name"),
        "owner_user_id": customer.get("owner_user_id") or deal.get("owner_user_id"),
        "owner_user_name": customer.get("owner_user_name") or deal.get("owner_user_name"),
        "title": f"执行{cadence['label']}：{customer_name}",
        "reason": "；".join(talking_points[:3]),
        "recommended_script": "\n".join(f"- {point}" for point in talking_points),
        "requires_approval": True,
    }

    return {
        "protocol": "followup.strategy.v1",
        "customer_id": customer_id,
        "customer_name": customer_name,
        "strategy_level": level,
        "strategy_label": cadence["label"],
        "priority": cadence["priority"],
        "next_touch_days": cadence["next_touch_days"],
        "preferred_channel": cadence["channel"],
        "last_follow_days": last_follow_days,
        "talking_points": talking_points,
        "open_deal": deal,
        "latest_risk": risk,
        "active_task_count": active_task_count,
        "pending_approval_count": pending_approval_count,
        "summary": f"{customer_name} 建议采用{cadence['label']}，{cadence['next_touch_days']} 天内通过 {cadence['channel']} 触达。",
        "recommended_actions": [action] if customer_id else [],
        "recommended_action_count": 1 if customer_id else 0,
        "execution_policy": {
            "auto_execute": False,
            "requires_human_approval": True,
            "reason": "跟进策略只生成任务草稿建议，必须经人工审批后进入动作链。",
        },
    }
