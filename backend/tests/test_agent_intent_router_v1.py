from app.modules.agent.intent_router import (
    INTENT_CUSTOMER_QUERY,
    INTENT_DATA_QUERY,
    INTENT_REPORT_QUERY,
    INTENT_RISK_ANALYSIS,
    INTENT_UNKNOWN,
    route_intent,
)


def test_intent_router_detects_risk_analysis_question():
    result = route_intent("这个客户为什么风险突然升高，竞品是不是介入了？")

    assert result.intent == INTENT_RISK_ANALYSIS
    assert result.confidence >= 0.6
    assert "风险" in result.matched_keywords


def test_intent_router_detects_data_query_question():
    result = route_intent("统计一下本月高风险客户有多少个，按负责人排行")

    assert result.intent == INTENT_DATA_QUERY
    assert result.confidence >= 0.6
    assert "统计" in result.matched_keywords


def test_intent_router_detects_report_query_question():
    result = route_intent("帮我总结一下这周经营周报里的风险趋势")

    assert result.intent == INTENT_REPORT_QUERY
    assert "周报" in result.matched_keywords


def test_intent_router_detects_customer_query_question():
    result = route_intent("这个客户最近一次跟进和报价是什么情况？")

    assert result.intent == INTENT_CUSTOMER_QUERY
    assert "客户" in result.matched_keywords


def test_intent_router_returns_unknown_for_empty_or_unclear_question():
    empty_result = route_intent("")
    unclear_result = route_intent("你好")

    assert empty_result.intent == INTENT_UNKNOWN
    assert empty_result.confidence == 0.0
    assert unclear_result.intent == INTENT_UNKNOWN
