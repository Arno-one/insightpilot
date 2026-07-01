from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RuleHit:
    rule_code: str
    rule_name: str
    score: int
    reason: str


def calculate_risk_score(customer: dict, deal: dict | None = None) -> dict:
    """V1 内置风险规则：规则负责打分，LLM 只负责解释和建议。"""
    now = datetime.now()
    hits: list[RuleHit] = []

    last_follow_up_at = customer.get("last_follow_up_at")
    if last_follow_up_at:
        days = (now - last_follow_up_at).days
        if days >= 30:
            hits.append(RuleHit("no_follow_30d", "超过 30 天未跟进", 35, f"客户已 {days} 天无跟进"))
        elif days >= 14:
            hits.append(RuleHit("no_follow_14d", "超过 14 天未跟进", 20, f"客户已 {days} 天无跟进"))

    if deal and deal.get("quoted_at"):
        quote_days = (now - deal["quoted_at"]).days
        if quote_days >= 14:
            hits.append(RuleHit("quote_no_response_14d", "报价后超过 14 天未回应", 35, f"报价后 {quote_days} 天无回应"))
        elif quote_days >= 7:
            hits.append(RuleHit("quote_no_response_7d", "报价后超过 7 天未回应", 20, f"报价后 {quote_days} 天无回应"))

    if customer.get("last_sentiment") == "negative":
        hits.append(RuleHit("negative_sentiment", "最近一次跟进情绪负面", 15, "最近一次沟通反馈偏负面"))

    if customer.get("competitor_involved"):
        hits.append(RuleHit("competitor_involved", "竞品介入", 20, "客户已明确提到竞品"))

    if not customer.get("next_follow_up_at"):
        hits.append(RuleHit("missing_next_follow", "下次跟进时间为空", 10, "当前客户没有明确下一步跟进时间"))

    if deal and (deal.get("amount") or 0) >= 80000:
        hits.append(RuleHit("high_value_deal", "商机金额较高", 10, "该客户商机金额较高，需要优先关注"))

    score = min(sum(hit.score for hit in hits), 100)
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"

    return {
        "risk_score": score,
        "risk_level": level,
        "rule_hits": [hit.__dict__ for hit in hits],
        "evidence": {
            "customer_id": customer.get("customer_id"),
            "last_follow_up_at": str(last_follow_up_at) if last_follow_up_at else None,
            "competitor_involved": bool(customer.get("competitor_involved")),
            "last_sentiment": customer.get("last_sentiment"),
        },
    }
