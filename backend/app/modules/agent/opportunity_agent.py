from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


STAGE_PROBABILITY = {
    "communicated": 0.2,
    "solution": 0.4,
    "quotation": 0.6,
    "won": 1.0,
    "lost": 0.0,
}


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


def _to_number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _heat_state(row: dict[str, Any], now: datetime) -> str:
    last_follow_days = _days_since(row.get("last_follow_up_at"), now)
    intent_level = str(row.get("intent_level") or "").lower()
    if row.get("competitor_involved"):
        return "at_risk"
    if intent_level == "high" and (last_follow_days is None or last_follow_days <= 7):
        return "hot"
    if last_follow_days is not None and last_follow_days >= 14:
        return "cooling"
    return "stable"


def _close_probability(row: dict[str, Any], heat_state: str) -> float:
    probability = STAGE_PROBABILITY.get(str(row.get("stage") or ""), 0.25)
    if str(row.get("intent_level") or "").lower() == "high":
        probability += 0.1
    if heat_state == "hot":
        probability += 0.05
    if heat_state == "cooling":
        probability -= 0.1
    if heat_state == "at_risk":
        probability -= 0.15
    if _to_number(row.get("quote_amount")) > 0:
        probability += 0.05
    return max(0.0, min(1.0, round(probability, 2)))


def _build_alerts(
    row: dict[str, Any],
    *,
    quote_timeout: bool,
    quote_age_days: int | None,
    heat_state: str,
    close_probability: float,
) -> list[str]:
    alerts: list[str] = []
    if quote_timeout:
        alerts.append(f"报价后 {quote_age_days} 天未记录有效响应")
    if heat_state == "cooling":
        alerts.append("最近跟进间隔过长，商机热度下降")
    if heat_state == "at_risk":
        alerts.append("客户存在竞品介入，成交概率承压")
    if close_probability >= 0.7:
        alerts.append("成交概率较高，适合推动关键决策确认")
    if str(row.get("close_result") or "open") != "open":
        alerts.append("商机已关闭，仅保留为复盘参考")
    return alerts


def _build_follow_up_suggestion(
    *,
    quote_timeout: bool,
    heat_state: str,
    close_probability: float,
) -> str:
    if close_probability >= 0.7:
        return "安排负责人推进成交确认，锁定下一步时间表。"
    if quote_timeout:
        return "优先回访报价反馈，确认预算、竞品和决策时间。"
    if heat_state in {"cooling", "at_risk"}:
        return "补一次高质量跟进，明确阻塞点并更新商机阶段。"
    return "保持常规跟进，继续观察客户反馈。"


def analyze_opportunities(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    quote_timeout_days: int = 7,
) -> dict[str, Any]:
    """扫描商机信号；V1 用确定性规则识别报价超时、热度变化、成交概率和跟进建议。"""
    now = now or datetime.now()
    items: list[dict[str, Any]] = []
    for row in rows:
        quote_age_days = _days_since(row.get("quoted_at"), now)
        quote_timeout = bool(_to_number(row.get("quote_amount")) > 0 and quote_age_days is not None and quote_age_days >= quote_timeout_days)
        heat_state = _heat_state(row, now)
        close_probability = _close_probability(row, heat_state)
        alerts = _build_alerts(
            row,
            quote_timeout=quote_timeout,
            quote_age_days=quote_age_days,
            heat_state=heat_state,
            close_probability=close_probability,
        )
        items.append(
            {
                "deal_id": row.get("deal_id"),
                "customer_id": row.get("customer_id"),
                "customer_name": row.get("customer_name"),
                "owner_user_id": row.get("owner_user_id"),
                "owner_user_name": row.get("owner_user_name"),
                "deal_name": row.get("deal_name"),
                "stage": row.get("stage"),
                "amount": _to_number(row.get("amount")),
                "quote_amount": _to_number(row.get("quote_amount")),
                "quoted_at": _coerce_datetime(row.get("quoted_at")).isoformat() if _coerce_datetime(row.get("quoted_at")) else None,
                "quote_age_days": quote_age_days,
                "quote_timeout": quote_timeout,
                "heat_state": heat_state,
                "close_probability": close_probability,
                "alerts": alerts,
                "follow_up_suggestion": _build_follow_up_suggestion(
                    quote_timeout=quote_timeout,
                    heat_state=heat_state,
                    close_probability=close_probability,
                ),
            }
        )

    timeout_items = [item for item in items if item["quote_timeout"]]
    heat_change_items = [item for item in items if item["heat_state"] in {"hot", "cooling", "at_risk"}]
    priority_items = sorted(
        items,
        key=lambda item: (len(item["alerts"]), item["close_probability"], item["quote_age_days"] or 0),
        reverse=True,
    )[:10]
    return {
        "protocol": "opportunity.scan.v1",
        "total": len(items),
        "quote_timeout_count": len(timeout_items),
        "heat_change_count": len(heat_change_items),
        "items": items,
        "priority_items": priority_items,
        "summary": f"扫描 {len(items)} 个商机，发现 {len(timeout_items)} 个报价超时、{len(heat_change_items)} 个热度变化信号。",
    }
