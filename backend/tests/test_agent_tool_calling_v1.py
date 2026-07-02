from app.modules.agent.platform.tool_registry import InternalToolRegistry, ToolDefinition, ToolExecutionContext
from app.modules.llm import client as llm_client


class _DummyDb:
    pass


def test_internal_tool_registry_lists_and_executes_registered_tools():
    calls: list[tuple[str, dict]] = []

    def sample_handler(context: ToolExecutionContext, payload: dict) -> dict:
        calls.append((context.run_id, payload))
        return {"echo": payload["value"] * 2}

    registry = InternalToolRegistry(
        [
            ToolDefinition(
                name="sample.double",
                description="把输入值翻倍，验证统一工具执行协议。",
                handler=sample_handler,
            )
        ]
    )
    result = registry.execute(
        "sample.double",
        ToolExecutionContext(tenant_id="demo_tenant", user_id="u_demo", run_id="run_demo", db=_DummyDb()),
        {"value": 6},
    )

    assert registry.list_tool_specs() == [
        {
            "name": "sample.double",
            "description": "把输入值翻倍，验证统一工具执行协议。",
        }
    ]
    assert result["tool_name"] == "sample.double"
    assert result["output"] == {"echo": 12}
    assert calls == [("run_demo", {"value": 6})]


def test_internal_tool_registry_rejects_unknown_tool():
    registry = InternalToolRegistry()

    try:
        registry.execute(
            "missing.tool",
            ToolExecutionContext(tenant_id="demo_tenant", user_id="u_demo", run_id="run_demo", db=_DummyDb()),
            {},
        )
    except ValueError as exc:
        assert str(exc) == "未注册的内部工具: missing.tool"
    else:
        raise AssertionError("未注册工具应当抛出 ValueError")


def test_plan_risk_tool_calls_falls_back_to_internal_minimal_sequence(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")

    plan = llm_client.plan_risk_tool_calls(
        customer={"customer_id": "cust_001", "customer_name": "上海样例客户"},
        deal={"deal_id": "deal_001", "stage": "quotation", "amount": 52000},
        risk_result={
            "risk_score": 68,
            "risk_level": "high",
            "rule_hits": [{"rule_name": "连续14天未跟进"}],
            "evidence": {},
        },
        available_tools=[
            {"name": "rag.retrieve_sales_context", "description": "检索销售知识"},
            {"name": "risk.generate_advice", "description": "生成风险建议"},
        ],
    )

    assert [step.tool_name for step in plan.steps] == [
        "rag.retrieve_sales_context",
        "risk.generate_advice",
    ]


def test_plan_risk_tool_calls_fallback_expands_to_customer_and_report_context(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")

    plan = llm_client.plan_risk_tool_calls(
        customer={
            "customer_id": "cust_001",
            "customer_name": "上海样例客户",
            "owner_user_id": "u_sales_001",
            "competitor_involved": 1,
            "last_follow_up_at": None,
            "next_follow_up_at": None,
        },
        deal={"deal_id": "deal_001", "stage": "quotation", "amount": 88000},
        risk_result={
            "risk_score": 76,
            "risk_level": "high",
            "rule_hits": [{"rule_name": "连续14天未跟进"}],
            "evidence": {},
        },
        available_tools=[
            {"name": "crm.get_customer_detail", "description": "拉取客户聚合详情"},
            {"name": "report.query", "description": "查询历史经营报告"},
            {"name": "rag.retrieve_sales_context", "description": "检索销售知识"},
            {"name": "risk.generate_advice", "description": "生成风险建议"},
        ],
    )

    assert [step.tool_name for step in plan.steps] == [
        "crm.get_customer_detail",
        "report.query",
        "rag.retrieve_sales_context",
        "risk.generate_advice",
    ]
    assert "上下文" in plan.thinking


def test_plan_risk_tool_calls_ensures_generate_advice_as_last_step(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "demo-key")

    def fake_structured_complete(system_prompt: str, user_message: str, schema):
        return llm_client.RiskToolPlan(
            thinking="先查，再给建议。",
            steps=[
                llm_client.RiskToolPlanStep(tool_name="risk.generate_advice", reason="先生成"),
                llm_client.RiskToolPlanStep(tool_name="crm.get_customer_detail", reason="再补详情"),
                llm_client.RiskToolPlanStep(tool_name="risk.generate_advice", reason="重复步骤"),
            ],
        )

    monkeypatch.setattr(llm_client, "structured_complete", fake_structured_complete)

    plan = llm_client.plan_risk_tool_calls(
        customer={"customer_id": "cust_001", "customer_name": "上海样例客户"},
        deal=None,
        risk_result={
            "risk_score": 55,
            "risk_level": "medium",
            "rule_hits": [{"rule_name": "客户沉默"}],
            "evidence": {},
        },
        available_tools=[
            {"name": "crm.get_customer_detail", "description": "拉取客户聚合详情"},
            {"name": "risk.generate_advice", "description": "生成风险建议"},
        ],
    )

    assert [step.tool_name for step in plan.steps] == [
        "crm.get_customer_detail",
        "risk.generate_advice",
    ]


def test_review_risk_tool_results_fallback_blocks_incomplete_advice(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")

    decision = llm_client.review_risk_tool_results(
        customer={"customer_id": "cust_001", "customer_name": "上海样例客户"},
        deal=None,
        risk_result={
            "risk_score": 68,
            "risk_level": "high",
            "rule_hits": [{"rule_name": "连续14天未跟进"}],
            "evidence": {},
        },
        rag_result={"status": "failed", "trace_id": None, "hit_count": 0},
        advice_data={"reason": "只有原因，其他字段缺失"},
    )

    assert decision.approved is False
    assert "缺少关键字段" in decision.review_note


def test_review_risk_tool_results_fallback_blocks_high_risk_without_context_evidence(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")

    decision = llm_client.review_risk_tool_results(
        customer={"customer_id": "cust_001", "customer_name": "上海样例客户"},
        deal={"deal_id": "deal_001", "amount": 88000},
        risk_result={
            "risk_score": 82,
            "risk_level": "high",
            "rule_hits": [{"rule_name": "连续14天未跟进"}],
            "evidence": {},
        },
        rag_result={"status": "failed", "trace_id": None, "hit_count": 0},
        advice_data={
            "reason": "客户长期未推进且风险较高。",
            "suggestion": "建议主管介入。",
            "task_type": "manager_intervention",
            "task_title": "主管介入高风险客户",
            "priority": "urgent",
            "recommended_script": "先确认采购时间与阻塞点。",
        },
    )

    assert decision.approved is False
    assert "证据" in decision.review_note
    assert decision.evidence_used == []


def test_review_risk_tool_results_fallback_blocks_duplicate_pending_approval(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")

    decision = llm_client.review_risk_tool_results(
        customer={"customer_id": "cust_001", "customer_name": "上海样例客户"},
        deal=None,
        risk_result={
            "risk_score": 61,
            "risk_level": "medium",
            "rule_hits": [{"rule_name": "客户沉默"}],
            "evidence": {},
        },
        rag_result={"status": "success", "trace_id": "trace_001", "hit_count": 2},
        advice_data={
            "reason": "客户跟进节奏变慢。",
            "suggestion": "建议补一次高质量回访。",
            "task_type": "quote_follow",
            "task_title": "补充客户回访",
            "priority": "high",
            "recommended_script": "先确认预算和决策时间。",
        },
        customer_detail={
            "approvals": [{"approval_id": "appr_001", "status": "pending"}],
            "tasks": [],
            "follow_ups": [],
        },
        tool_executions=[{"tool_name": "crm.get_customer_detail"}],
    )

    assert decision.approved is False
    assert "待审批" in decision.review_note
    assert "crm.get_customer_detail" in decision.evidence_used


def test_review_risk_tool_results_fallback_approves_complete_advice(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "deepseek_api_key", "")

    decision = llm_client.review_risk_tool_results(
        customer={"customer_id": "cust_001", "customer_name": "上海样例客户"},
        deal=None,
        risk_result={
            "risk_score": 68,
            "risk_level": "high",
            "rule_hits": [{"rule_name": "连续14天未跟进"}],
            "evidence": {},
        },
        rag_result={"status": "success", "trace_id": "trace_001", "hit_count": 3},
        advice_data={
            "reason": "客户长期未推进且存在竞品介入迹象。",
            "suggestion": "建议主管介入，先确认客户真实采购时间和阻塞点。",
            "task_type": "manager_intervention",
            "task_title": "主管介入高风险客户",
            "priority": "urgent",
            "recommended_script": "这次先不推动成交，只确认项目节奏和真实顾虑。",
        },
        customer_detail={
            "approvals": [],
            "tasks": [],
            "follow_ups": [{"follow_up_id": "fu_001"}],
        },
        related_reports=[{"report_id": "report_001", "summary": "最近两周客户推进速度明显放缓。"}],
        tool_executions=[
            {"tool_name": "crm.get_customer_detail"},
            {"tool_name": "report.query"},
            {"tool_name": "rag.retrieve_sales_context"},
        ],
    )

    assert decision.approved is True
    assert "证据" in decision.summary
    assert decision.evidence_used == [
        "rag.retrieve_sales_context",
        "crm.get_customer_detail",
        "report.query",
    ]
