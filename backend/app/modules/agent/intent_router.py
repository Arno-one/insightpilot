from dataclasses import dataclass


INTENT_RISK_ANALYSIS = "risk_analysis"
INTENT_BUSINESS_ANALYSIS = "business_analysis"
INTENT_MANAGER_DECISION = "manager_decision"
INTENT_ACTION_EXECUTION = "action_execution"
INTENT_CUSTOMER_PROFILE = "customer_profile"
INTENT_OPPORTUNITY_ANALYSIS = "opportunity_analysis"
INTENT_FOLLOW_UP_STRATEGY = "follow_up_strategy"
INTENT_CUSTOMER_QUERY = "customer_query"
INTENT_REPORT_QUERY = "report_query"
INTENT_DATA_QUERY = "data_query"
INTENT_UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentRouteResult:
    intent: str
    confidence: float
    reason: str
    matched_keywords: list[str]

    def model_dump(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "reason": self.reason,
            "matched_keywords": self.matched_keywords,
        }


INTENT_KEYWORDS: dict[str, list[str]] = {
    INTENT_BUSINESS_ANALYSIS: [
        "经营分析",
        "为什么",
        "原因",
        "下降",
        "下滑",
        "增长",
        "趋势",
        "异常",
        "指标",
        "归因",
        "转化率",
        "收入",
        "业绩",
        "负责人转化率",
        "风险最高",
        "topn",
    ],
    INTENT_MANAGER_DECISION: [
        "经营决策",
        "决策建议",
        "建议动作",
        "优先处理",
        "优先跟进",
        "重点跟进",
        "该优先",
        "该处理",
        "老板",
        "销售需要",
        "哪些销售",
        "哪些客户",
        "怎么处理",
        "下一步动作",
    ],
    INTENT_ACTION_EXECUTION: [
        "执行",
        "提交审批",
        "进入审批",
        "创建审批",
        "生成审批",
        "创建任务",
        "发通知",
        "发送通知",
        "安排日程",
        "创建日程",
        "发邮件",
        "发送邮件",
        "落地",
    ],
    INTENT_CUSTOMER_PROFILE: [
        "客户画像",
        "画像",
        "客户标签",
        "标签",
        "客户记忆",
        "生成画像",
        "更新画像",
        "画像摘要",
    ],
    INTENT_OPPORTUNITY_ANALYSIS: [
        "商机分析",
        "商机",
        "报价",
        "报价超时",
        "成交概率",
        "成交机会",
        "热度",
        "热度变化",
        "跟进建议",
        "推进成交",
        "开放商机",
        "重点商机",
    ],
    INTENT_FOLLOW_UP_STRATEGY: [
        "跟进策略",
        "跟进计划",
        "回访策略",
        "触达策略",
        "沟通策略",
        "跟进话术",
        "回访话术",
        "怎么跟进",
        "如何跟进",
        "下一次跟进",
        "客户跟进",
    ],
    INTENT_DATA_QUERY: [
        "多少",
        "几个",
        "总数",
        "统计",
        "查询",
        "排行",
        "top",
        "sql",
        "数据",
        "本月",
        "同比",
        "环比",
    ],
    INTENT_RISK_ANALYSIS: [
        "风险",
        "流失",
        "预警",
        "竞品",
        "高风险",
        "跟进断档",
        "为什么升高",
        "风险原因",
    ],
    INTENT_REPORT_QUERY: [
        "报告",
        "日报",
        "周报",
        "月报",
        "经营简报",
        "趋势",
        "复盘",
        "总结",
    ],
    INTENT_CUSTOMER_QUERY: [
        "客户",
        "联系人",
        "商机",
        "报价",
        "跟进",
        "回访",
        "负责人",
        "客户画像",
    ],
}

INTENT_REASON_LABELS = {
    INTENT_RISK_ANALYSIS: "命中风险分析相关表达",
    INTENT_BUSINESS_ANALYSIS: "命中经营分析相关表达",
    INTENT_MANAGER_DECISION: "命中经营决策相关表达",
    INTENT_ACTION_EXECUTION: "命中执行动作相关表达",
    INTENT_CUSTOMER_PROFILE: "命中客户画像相关表达",
    INTENT_OPPORTUNITY_ANALYSIS: "命中商机分析相关表达",
    INTENT_FOLLOW_UP_STRATEGY: "命中跟进策略相关表达",
    INTENT_CUSTOMER_QUERY: "命中客户经营相关表达",
    INTENT_REPORT_QUERY: "命中经营报告相关表达",
    INTENT_DATA_QUERY: "命中数据查询相关表达",
    INTENT_UNKNOWN: "暂未命中明确意图",
}


def _normalize_question(question: str) -> str:
    return " ".join(str(question or "").lower().split()).strip()


def _matched_keywords(question: str, keywords: list[str]) -> list[str]:
    normalized = _normalize_question(question)
    return [keyword for keyword in keywords if keyword.lower() in normalized]


def _score_intent(question: str, intent: str, keywords: list[str]) -> tuple[int, list[str]]:
    matched = _matched_keywords(question, keywords)
    score = len(matched)
    # 中文注释：数据查询和风险问题都可能提到“客户”，用更具体的关键词数量作为第一优先级。
    if intent == INTENT_DATA_QUERY and any(keyword in matched for keyword in ["多少", "几个", "统计", "排行", "sql"]):
        score += 2
    if intent == INTENT_BUSINESS_ANALYSIS and any(
        keyword in matched for keyword in ["为什么", "原因", "下降", "趋势", "异常", "归因", "转化率", "风险最高"]
    ):
        score += 3
    if intent == INTENT_MANAGER_DECISION and any(
        keyword in matched for keyword in ["建议动作", "优先处理", "重点跟进", "该优先", "哪些客户", "哪些销售", "下一步动作"]
    ):
        score += 4
    if intent == INTENT_ACTION_EXECUTION and any(
        keyword in matched for keyword in ["提交审批", "进入审批", "创建任务", "发通知", "安排日程", "发邮件", "执行"]
    ):
        score += 8
    if intent == INTENT_CUSTOMER_PROFILE and any(keyword in matched for keyword in ["客户画像", "画像", "客户标签", "生成画像"]):
        score += 5
    if intent == INTENT_OPPORTUNITY_ANALYSIS and any(
        keyword in matched for keyword in ["商机分析", "报价超时", "成交概率", "热度变化", "跟进建议", "重点商机"]
    ):
        score += 5
    if intent == INTENT_FOLLOW_UP_STRATEGY and any(
        keyword in matched for keyword in ["跟进策略", "跟进计划", "回访策略", "触达策略", "跟进话术", "怎么跟进", "如何跟进"]
    ):
        score += 6
    if intent == INTENT_RISK_ANALYSIS and any(keyword in matched for keyword in ["风险", "流失", "预警", "竞品"]):
        score += 3
    if intent == INTENT_REPORT_QUERY and any(keyword in matched for keyword in ["报告", "日报", "周报", "月报", "经营简报"]):
        score += 2
    return score, matched


def route_intent(question: str) -> IntentRouteResult:
    """V1 使用确定性关键词路由，先保证稳定可测，后续再接 Planner / LLM Router。"""
    normalized = _normalize_question(question)
    if not normalized:
        return IntentRouteResult(
            intent=INTENT_UNKNOWN,
            confidence=0.0,
            reason="问题为空，无法判断意图",
            matched_keywords=[],
        )

    candidates: list[tuple[int, str, list[str]]] = []
    for intent, keywords in INTENT_KEYWORDS.items():
        score, matched = _score_intent(normalized, intent, keywords)
        candidates.append((score, intent, matched))

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_intent, matched_keywords = candidates[0]
    if best_score <= 0:
        return IntentRouteResult(
            intent=INTENT_UNKNOWN,
            confidence=0.2,
            reason=INTENT_REASON_LABELS[INTENT_UNKNOWN],
            matched_keywords=[],
        )

    confidence = min(0.95, 0.45 + best_score * 0.15)
    return IntentRouteResult(
        intent=best_intent,
        confidence=confidence,
        reason=INTENT_REASON_LABELS[best_intent],
        matched_keywords=matched_keywords,
    )
