import json
import logging
import time
from typing import Type

from pydantic import BaseModel, Field

from app.core.config import settings
from app.modules.llm.usage import estimate_llm_cost, extract_token_usage, record_llm_call

logger = logging.getLogger(__name__)


class RiskAdvice(BaseModel):
    """客户风险建议的结构化输出，便于直接落库和生成审批草稿。"""

    reason: str = Field(..., description="风险原因说明")
    suggestion: str = Field(..., description="处理建议")
    task_type: str = Field(..., description="任务类型")
    task_title: str = Field(..., description="任务标题")
    priority: str = Field(..., description="任务优先级")
    recommended_script: str = Field(..., description="推荐沟通话术")


class RiskToolPlanStep(BaseModel):
    """风险 Agent 的单步工具计划，第一阶段只编排内部工具。"""

    tool_name: str = Field(..., description="需要调用的内部工具名")
    reason: str = Field(..., description="为什么要调用这个工具")


class RiskToolPlan(BaseModel):
    """风险 Agent 规划结果，先决定工具顺序，再进入执行与复核。"""

    thinking: str = Field(..., description="本次处置思路摘要")
    steps: list[RiskToolPlanStep] = Field(..., min_length=1, description="工具调用步骤列表")


class RiskReviewDecision(BaseModel):
    """风险 Agent 复核结果，第一阶段仍坚持人审后落地。"""

    approved: bool = Field(..., description="当前建议是否可以进入人工审批草稿")
    summary: str = Field(..., description="本次复核总结")
    review_note: str = Field(..., description="复核意见")
    evidence_used: list[str] = Field(default_factory=list, description="本次复核实际参考的证据来源")


class ReportNarrative(BaseModel):
    """经营日报的结构化摘要输出，便于直接写入 business_report。"""

    summary: str = Field(..., description="日报摘要")
    suggestions: str = Field(..., description="经营建议")


class RiskConversationReply(BaseModel):
    """Risk Agent 对话回复结构，方便后续扩展多字段会话输出。"""

    reply: str = Field(..., description="Risk Agent 针对当前客户与当前问题的回复")


def _risk_tool_names(available_tools: list[dict[str, str]]) -> set[str]:
    return {tool["name"] for tool in available_tools}


def _has_customer_follow_up_gap(customer: dict) -> bool:
    return not customer.get("last_follow_up_at") or not customer.get("next_follow_up_at")


def _deal_amount_value(deal: dict | None) -> float:
    if not deal:
        return 0.0
    for field_name in ("amount", "quote_amount"):
        value = deal.get(field_name)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _finalize_risk_plan_steps(
    steps: list[RiskToolPlanStep],
    available_tools: list[dict[str, str]],
) -> list[RiskToolPlanStep]:
    """统一清洗 Planner 步骤，确保工具合法、去重且最终会生成结构化建议。"""
    available_tool_names = _risk_tool_names(available_tools)
    deduped_steps: list[RiskToolPlanStep] = []
    seen_tools: set[str] = set()
    for step in steps:
        if step.tool_name not in available_tool_names or step.tool_name in seen_tools:
            continue
        deduped_steps.append(step)
        seen_tools.add(step.tool_name)

    if "risk.generate_advice" in available_tool_names and "risk.generate_advice" not in seen_tools:
        deduped_steps.append(
            RiskToolPlanStep(
                tool_name="risk.generate_advice",
                reason="在上下文补齐后生成结构化风险建议，供 Reviewer 判断是否进入人工审批。",
            )
        )
    elif "risk.generate_advice" in seen_tools:
        advice_step = next(step for step in deduped_steps if step.tool_name == "risk.generate_advice")
        deduped_steps = [step for step in deduped_steps if step.tool_name != "risk.generate_advice"] + [advice_step]

    return deduped_steps


def _json_schema_instruction(schema: Type[BaseModel]) -> str:
    """直接输出 Pydantic 的 JSON Schema，方便嵌套结构稳定返回。"""
    return json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)


def _strip_code_fence(text: str) -> str:
    raw = text.strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def structured_complete(
    system_prompt: str,
    user_message: str,
    schema: Type[BaseModel],
    *,
    tenant_id: str = "system",
    user_id: str | None = None,
    source: str | None = None,
    metadata_json: dict | None = None,
) -> BaseModel | None:
    """调用 DeepSeek 并校验结构化 JSON；失败返回 None，由业务层降级处理。"""
    if not settings.deepseek_api_key:
        logger.warning("未配置 DEEPSEEK_API_KEY，跳过 LLM 调用")
        return None

    model_name = "deepseek-chat"
    started = time.perf_counter()
    log_source = source or schema.__name__
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        response = client.chat.completions.create(
            model=model_name,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n\n"
                        "请严格输出 JSON，不要输出 Markdown，不要输出额外解释。\n"
                        f"JSON 格式如下：\n{_json_schema_instruction(schema)}"
                    ),
                },
                {"role": "user", "content": user_message},
            ],
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        usage = extract_token_usage(response)
        raw = response.choices[0].message.content or ""
        data = json.loads(_strip_code_fence(raw))
        parsed = schema.model_validate(data)
        estimated_cost = estimate_llm_cost(
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
        )
        record_llm_call(
            tenant_id=tenant_id,
            user_id=user_id,
            source=log_source,
            model=model_name,
            status="success",
            latency_ms=elapsed_ms,
            estimated_cost=estimated_cost,
            metadata_json=metadata_json,
            **usage,
        )
        return parsed
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        record_llm_call(
            tenant_id=tenant_id,
            user_id=user_id,
            source=log_source,
            model=model_name,
            status="failed",
            latency_ms=elapsed_ms,
            estimated_cost=estimate_llm_cost(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            ),
            error_message=str(exc)[:1000],
            metadata_json=metadata_json,
            **usage,
        )
        logger.warning("LLM 结构化调用失败，自动降级: %s", exc)
        return None


def fallback_risk_advice(customer: dict, risk_result: dict) -> RiskAdvice:
    """LLM 不可用时的确定性降级建议，保证主流程不断。"""
    customer_name = customer.get("customer_name") or customer.get("customer_id")
    level = risk_result["risk_level"]
    rule_names = "、".join(hit["rule_name"] for hit in risk_result["rule_hits"]) or "暂无明显规则命中"
    is_high = level == "high"
    task_type = "manager_intervention" if is_high else "quote_follow"
    priority = "urgent" if is_high else "medium"

    return RiskAdvice(
        reason=f"{customer_name} 当前风险等级为 {level}，主要命中规则：{rule_names}。",
        suggestion="建议先确认客户真实顾虑和下一步决策时间；如涉及高金额、竞品介入或长期无回应，应由销售主管介入。",
        task_type=task_type,
        task_title=f"{'主管介入' if is_high else '跟进'}{customer_name} 风险客户",
        priority=priority,
        recommended_script="您好，我这边不是催您做决定，只是想确认之前方案是否还有继续评估的必要。如果优先级有变化，我们也可以按您的节奏调整后续沟通。",
    )


def fallback_risk_tool_plan(
    customer: dict,
    deal: dict | None,
    risk_result: dict,
    available_tools: list[dict[str, str]],
    customer_memory: dict | None = None,
) -> RiskToolPlan:
    """LLM 不可用时的保底规划，也尽量按风险场景动态选择最合适的工具。"""
    available_tool_names = _risk_tool_names(available_tools)
    steps: list[RiskToolPlanStep] = []
    memory_summary = customer_memory.get("summary_json", {}) if isinstance(customer_memory, dict) else {}
    memory_approval_state = memory_summary.get("approval_state", {}) if isinstance(memory_summary, dict) else {}
    memory_task_state = memory_summary.get("task_state", {}) if isinstance(memory_summary, dict) else {}
    memory_risk_state = memory_summary.get("risk_state", {}) if isinstance(memory_summary, dict) else {}
    needs_customer_detail = bool(
        risk_result.get("risk_level") == "high"
        or customer.get("competitor_involved")
        or _has_customer_follow_up_gap(customer)
        or memory_approval_state.get("pending_count", 0)
        or memory_task_state.get("active_count", 0)
        or memory_risk_state.get("recent_medium_or_high_risk_count", 0)
    )
    needs_report_context = bool(
        risk_result.get("risk_score", 0) >= 60
        or _deal_amount_value(deal) >= 50000
        or memory_risk_state.get("latest_risk_level") == "high"
        or memory_summary.get("report_state", {}).get("report_count", 0)
    )

    if needs_customer_detail and "crm.get_customer_detail" in available_tool_names:
        steps.append(
            RiskToolPlanStep(
                tool_name="crm.get_customer_detail",
                reason="先补齐该客户最近的风险、审批、任务和跟进上下文，避免建议只看当前快照。",
            )
        )
    if needs_report_context and "report.query" in available_tool_names:
        steps.append(
            RiskToolPlanStep(
                tool_name="report.query",
                reason="补充近期经营报告和风险趋势，判断当前客户问题是否已连续出现。",
            )
        )
    if "rag.retrieve_sales_context" in available_tool_names:
        steps.append(
            RiskToolPlanStep(
                tool_name="rag.retrieve_sales_context",
                reason="先补销售知识和历史话术上下文，避免只靠规则分数给建议。",
            )
        )
    steps = _finalize_risk_plan_steps(steps, available_tools)
    if not steps:
        steps = [
            RiskToolPlanStep(
                tool_name="risk.generate_advice",
                reason="当前没有其他可用工具时，至少生成结构化风险建议。",
            )
        ]
    selected_tool_names = [step.tool_name for step in steps]
    return RiskToolPlan(
        thinking=(
            "先结合客户长期记忆和当前风险等级补齐经营上下文，再生成结构化建议，最后交给 Reviewer 判定是否进入人工审批。"
            if any(tool_name in selected_tool_names for tool_name in ("crm.get_customer_detail", "report.query"))
            else "先结合已有记忆补充可用上下文，再生成结构化建议，最后交给 Reviewer 判定是否进入人工审批。"
        ),
        steps=steps,
    )


def plan_risk_tool_calls(
    customer: dict,
    deal: dict | None,
    risk_result: dict,
    available_tools: list[dict[str, str]],
    customer_memory: dict | None = None,
) -> RiskToolPlan:
    """让 Planner 决定本次风险处置需要按什么顺序调用内部工具。"""
    system_prompt = (
        "你是 InsightPilot 风险 Agent 的 Planner。"
        "你只能从给定内部工具里挑选最少步骤，不能创建正式任务，不能跳过人工审批。"
        "当前阶段只允许规划 Review 之前的分析工具，不要输出审批创建动作。"
        "如果客户风险较高、跟进缺口明显、历史记忆显示已有重复风险，或需要历史经营视角，可以优先选择 CRM / Report 工具补充上下文。"
    )
    user_message = json.dumps(
        {
            "customer": customer,
            "deal": deal,
            "risk_result": risk_result,
            "customer_memory": customer_memory or {},
            "available_tools": available_tools,
            "planning_rules": [
                "优先选择能补齐上下文和生成结构化建议的工具",
                "当客户跟进缺口明显、审批任务较多或高风险时，可以先用 crm.get_customer_detail",
                "当需要近期经营趋势、历史风险摘要或高金额商机背景时，可以用 report.query",
                "如果客户长期记忆已经显示重复风险、待审批动作或活跃任务，需要先补上下文再给新建议",
                "步骤按实际执行顺序输出",
                "不要输出未提供的工具名",
                "不要输出 review 或审批创建动作",
            ],
        },
        ensure_ascii=False,
        default=str,
    )
    plan = structured_complete(system_prompt, user_message, RiskToolPlan)
    if not plan:
        return fallback_risk_tool_plan(customer, deal, risk_result, available_tools, customer_memory=customer_memory)

    valid_steps = _finalize_risk_plan_steps(plan.steps, available_tools)
    if not valid_steps:
        return fallback_risk_tool_plan(customer, deal, risk_result, available_tools, customer_memory=customer_memory)
    return RiskToolPlan(thinking=plan.thinking, steps=valid_steps)


def generate_risk_advice(
    customer: dict,
    deal: dict | None,
    risk_result: dict,
    rag_context: str = "",
    customer_memory: dict | None = None,
) -> RiskAdvice:
    """生成客户风险解释、建议和任务草稿。"""
    system_prompt = (
        "你是 InsightPilot 的企业运营参谋。"
        "风险分由规则引擎计算，你只能基于规则命中、客户资料、客户长期记忆和知识库上下文生成解释和建议。"
        "不要声称已经联系客户，不要绕过人工审批。"
    )
    user_message = json.dumps(
        {
            "customer": customer,
            "deal": deal,
            "risk_result": risk_result,
            "rag_context": rag_context,
            "customer_memory": customer_memory or {},
            "allowed_task_types": [
                "quote_follow",
                "objection_handle",
                "manager_intervention",
                "reactivation",
            ],
            "allowed_priorities": ["low", "medium", "high", "urgent"],
        },
        ensure_ascii=False,
        default=str,
    )
    advice = structured_complete(system_prompt, user_message, RiskAdvice)
    return advice or fallback_risk_advice(customer, risk_result)


def _risk_level_label(level: str | None) -> str:
    labels = {
        "high": "高风险",
        "medium": "中风险",
        "low": "低风险",
    }
    return labels.get(level or "", level or "待评估")


def fallback_risk_chat_reply(
    customer: dict,
    latest_risk: dict | None,
    customer_memory: dict | None,
    conversation_memory: dict | None,
    user_message: str,
) -> str:
    """LLM 不可用时给出稳定可测的对话回复，先保证有记忆、有上下文、能落地。"""
    latest_risk = latest_risk or {}
    customer_memory = customer_memory or {}
    conversation_memory = conversation_memory or {}
    summary_json = customer_memory.get("summary_json", {}) if isinstance(customer_memory, dict) else {}
    risk_state = summary_json.get("risk_state", {}) if isinstance(summary_json, dict) else {}
    approval_state = summary_json.get("approval_state", {}) if isinstance(summary_json, dict) else {}
    task_state = summary_json.get("task_state", {}) if isinstance(summary_json, dict) else {}
    follow_up_state = summary_json.get("follow_up_state", {}) if isinstance(summary_json, dict) else {}

    customer_name = customer.get("customer_name") or customer.get("customer_id") or "该客户"
    risk_level = latest_risk.get("risk_level") or risk_state.get("latest_risk_level")
    risk_score = latest_risk.get("risk_score") or risk_state.get("latest_risk_score")
    latest_reason = latest_risk.get("llm_reason") or risk_state.get("latest_reason")
    latest_suggestion = latest_risk.get("llm_suggestion") or risk_state.get("latest_suggestion")
    pending_approvals = int(approval_state.get("pending_count", 0) or 0)
    active_tasks = int(task_state.get("active_count", 0) or 0)
    latest_follow_up_at = follow_up_state.get("latest_follow_up_at") or customer.get("last_follow_up_at")
    history_summary = str(conversation_memory.get("history_summary") or "")
    normalized_message = str(user_message or "")

    parts = [
        f"结合当前客户资料，{customer_name} 现在更接近{_risk_level_label(risk_level)}场景"
        + (f"，最近风险分约 {risk_score}。" if risk_score not in (None, "") else "。"),
    ]

    if any(keyword in normalized_message for keyword in ["为什么", "原因", "风险"]):
        if latest_reason:
            parts.append(f"当前最核心的风险原因是：{latest_reason}")
        else:
            parts.append("当前还没有足够新的风险解释，建议先补一轮客户现状确认。")
    elif any(keyword in normalized_message for keyword in ["回访", "跟进", "联系", "沟通"]):
        parts.append("建议下一次沟通先确认真实采购时间、预算是否变化，以及竞品比较目前卡在哪一步。")
    elif any(keyword in normalized_message for keyword in ["审批", "任务", "执行"]):
        if pending_approvals:
            parts.append(f"这个客户当前还有 {pending_approvals} 条待审批动作，优先别重复创建新动作。")
        elif active_tasks:
            parts.append(f"这个客户当前已有 {active_tasks} 条执行中任务，建议先确认现有动作效果。")
        else:
            parts.append("当前还没有明显的待审批或执行中动作，可以先把问题澄清清楚，再决定是否升级为任务。")
    elif latest_suggestion:
        parts.append(f"如果现在要推进，我更建议：{latest_suggestion}")
    else:
        parts.append("建议先把客户真实顾虑、内部决策人状态和下一次跟进时间补齐，再决定后续动作。")

    if latest_follow_up_at:
        parts.append(f"现有记录里最近一次跟进时间是 {latest_follow_up_at}，对话里最好先核对这之后是否又出现了新变化。")
    if history_summary:
        parts.append("我会继续沿用更早对话的摘要，不会把这位客户当成全新对象重新分析。")

    return "\n".join(parts)


def generate_risk_chat_reply(
    customer: dict,
    latest_risk: dict | None,
    customer_memory: dict | None,
    conversation_memory: dict | None,
    user_message: str,
) -> str:
    """生成 Risk Agent 的客户对话回复；LLM 失败时自动降级为规则回复。"""
    system_prompt = (
        "你是 InsightPilot 的 Risk Agent。"
        "你只负责围绕单个客户给出经营与跟进建议，不能虚构已经执行过的动作。"
        "你必须结合客户长期记忆和当前会话记忆，避免把每次问题都当成全新上下文。"
        "回答保持简洁、可执行，优先指出下一步最值得做的动作。"
    )
    user_payload = {
        "customer": customer,
        "latest_risk": latest_risk or {},
        "customer_memory": customer_memory or {},
        "conversation_memory": {
            "history_summary": (conversation_memory or {}).get("history_summary", ""),
            "recent_messages": (conversation_memory or {}).get("recent_messages", []),
        },
        "current_user_message": user_message,
        "response_rules": [
            "不要声称已经调用外部系统或已经联系客户",
            "如果存在长期记忆或历史摘要，要显式基于这些信息回答",
            "优先输出下一步建议，不要写成空泛鸡汤",
        ],
    }
    reply = structured_complete(
        system_prompt,
        json.dumps(user_payload, ensure_ascii=False, default=str),
        RiskConversationReply,
    )
    if reply and reply.reply.strip():
        return reply.reply.strip()
    return fallback_risk_chat_reply(customer, latest_risk, customer_memory, conversation_memory, user_message)


def _review_evidence_snapshot(
    rag_result: dict,
    customer_detail: dict | None,
    related_reports: list[dict] | None,
    tool_executions: list[dict] | None,
    customer_memory: dict | None = None,
) -> dict[str, object]:
    """把 Reviewer 会用到的上下文证据压缩成简单快照，便于规则和 LLM 共用。"""
    related_reports = related_reports or []
    tool_executions = tool_executions or []
    customer_detail = customer_detail or {}
    customer_memory = customer_memory or {}

    approvals = customer_detail.get("approvals", []) if isinstance(customer_detail, dict) else []
    tasks = customer_detail.get("tasks", []) if isinstance(customer_detail, dict) else []
    follow_ups = customer_detail.get("follow_ups", []) if isinstance(customer_detail, dict) else []
    memory_summary = customer_memory.get("summary_json", {}) if isinstance(customer_memory, dict) else {}

    evidence_used: list[str] = []
    if rag_result.get("status") == "success" and rag_result.get("hit_count", 0):
        evidence_used.append("rag.retrieve_sales_context")
    if customer_detail:
        evidence_used.append("crm.get_customer_detail")
    if related_reports:
        evidence_used.append("report.query")
    if customer_memory:
        evidence_used.append("customer_memory")

    pending_approvals = sum(1 for item in approvals if item.get("status") == "pending")
    active_tasks = sum(1 for item in tasks if item.get("status") in {"pending", "in_progress"})
    if not pending_approvals:
        pending_approvals = int(memory_summary.get("approval_state", {}).get("pending_count", 0) or 0)
    if not active_tasks:
        active_tasks = int(memory_summary.get("task_state", {}).get("active_count", 0) or 0)
    follow_up_count = len(follow_ups)
    if not follow_up_count:
        follow_up_count = int(memory_summary.get("follow_up_state", {}).get("count", 0) or 0)
    report_count = len(related_reports)
    if not report_count:
        report_count = int(memory_summary.get("report_state", {}).get("report_count", 0) or 0)

    return {
        "evidence_used": evidence_used,
        "has_context_evidence": bool(evidence_used),
        "pending_approvals": pending_approvals,
        "active_tasks": active_tasks,
        "follow_up_count": follow_up_count,
        "report_count": report_count,
        "memory_summary_text": customer_memory.get("summary_text", "") if isinstance(customer_memory, dict) else "",
        "tool_names": [item.get("tool_name") for item in tool_executions if item.get("tool_name")],
    }


def fallback_risk_review_decision(
    risk_result: dict,
    rag_result: dict,
    advice_data: dict | None,
    customer_detail: dict | None = None,
    related_reports: list[dict] | None = None,
    tool_executions: list[dict] | None = None,
    customer_memory: dict | None = None,
) -> RiskReviewDecision:
    """LLM 不可用时的规则化 Reviewer，除了结构完整性，也会参考上下文证据与重复处置风险。"""
    required_fields = ["reason", "suggestion", "task_type", "task_title", "priority", "recommended_script"]
    missing_fields = [field for field in required_fields if not advice_data or not advice_data.get(field)]
    evidence = _review_evidence_snapshot(
        rag_result,
        customer_detail,
        related_reports,
        tool_executions,
        customer_memory=customer_memory,
    )
    if missing_fields:
        return RiskReviewDecision(
            approved=False,
            summary="建议信息不完整，暂不进入人工审批草稿。",
            review_note=f"缺少关键字段：{', '.join(missing_fields)}",
            evidence_used=evidence["evidence_used"],
        )
    if risk_result.get("risk_level") == "high" and not evidence["has_context_evidence"]:
        return RiskReviewDecision(
            approved=False,
            summary="高风险客户缺少充分证据支撑，暂不进入人工审批草稿。",
            review_note="当前没有拿到 CRM 详情、经营报告或有效 RAG 上下文，建议先补证据再提交审批。",
            evidence_used=evidence["evidence_used"],
        )
    if evidence["pending_approvals"]:
        return RiskReviewDecision(
            approved=False,
            summary="客户已存在待审批动作，先避免重复创建新的审批草稿。",
            review_note=f"该客户当前已有 {evidence['pending_approvals']} 条待审批记录，建议先处理存量审批。",
            evidence_used=evidence["evidence_used"],
        )
    if evidence["active_tasks"] and risk_result.get("risk_level") != "high":
        return RiskReviewDecision(
            approved=False,
            summary="客户已有在执行任务，当前建议先不重复进入审批。",
            review_note=f"检测到 {evidence['active_tasks']} 条活跃任务，建议先确认现有动作效果，再决定是否追加处置。",
            evidence_used=evidence["evidence_used"],
        )
    return RiskReviewDecision(
        approved=True,
        summary="建议结构完整，且已有足够证据支持，可以进入人工审批草稿。",
        review_note="已校验建议字段、风险等级、上下文证据和重复处置风险，保持先审后落地。",
        evidence_used=evidence["evidence_used"],
    )


def review_risk_tool_results(
    customer: dict,
    deal: dict | None,
    risk_result: dict,
    rag_result: dict,
    advice_data: dict | None,
    customer_detail: dict | None = None,
    related_reports: list[dict] | None = None,
    tool_executions: list[dict] | None = None,
    customer_memory: dict | None = None,
) -> RiskReviewDecision:
    """让 Reviewer 判断当前建议是否值得进入审批草稿。"""
    evidence = _review_evidence_snapshot(
        rag_result,
        customer_detail,
        related_reports,
        tool_executions,
        customer_memory=customer_memory,
    )
    system_prompt = (
        "你是 InsightPilot 风险 Agent 的 Reviewer。"
        "你只能判断当前建议是否应进入人工审批草稿，不能直接创建正式任务。"
        "如果建议字段缺失、风险解释空泛、证据不足，或客户已有待审批/在执行动作而重复创建处置，应拒绝通过。"
        "客户长期记忆可以作为辅助证据，但不能忽略当前风险快照。"
    )
    user_message = json.dumps(
        {
            "customer": customer,
            "deal": deal,
            "risk_result": risk_result,
            "rag_result": {
                "status": rag_result.get("status"),
                "hit_count": rag_result.get("hit_count", 0),
                "trace_id": rag_result.get("trace_id"),
            },
            "customer_detail_snapshot": {
                "approval_count": len((customer_detail or {}).get("approvals", [])) if isinstance(customer_detail, dict) else 0,
                "pending_approval_count": evidence["pending_approvals"],
                "task_count": len((customer_detail or {}).get("tasks", [])) if isinstance(customer_detail, dict) else 0,
                "active_task_count": evidence["active_tasks"],
                "follow_up_count": evidence["follow_up_count"],
            },
            "report_snapshot": {
                "report_count": evidence["report_count"],
                "latest_report_summary": (related_reports or [{}])[0].get("summary", "")[:200] if related_reports else "",
            },
            "tool_execution_summary": {
                "tool_names": evidence["tool_names"],
                "evidence_used": evidence["evidence_used"],
            },
            "customer_memory": {
                "summary_text": evidence["memory_summary_text"][:300],
                "summary_json": (customer_memory or {}).get("summary_json", {}) if isinstance(customer_memory, dict) else {},
            },
            "advice": advice_data,
            "review_rules": [
                "保持先审后落地",
                "只有建议结构完整、结论明确且证据足够时才允许 approved=true",
                "如果客户已有待审批或已有活跃任务，要谨慎避免重复处置",
                "review_note 必须说清楚通过或拒绝的原因",
            ],
        },
        ensure_ascii=False,
        default=str,
    )
    decision = structured_complete(system_prompt, user_message, RiskReviewDecision)
    return decision or fallback_risk_review_decision(
        risk_result,
        rag_result,
        advice_data,
        customer_detail=customer_detail,
        related_reports=related_reports,
        tool_executions=tool_executions,
        customer_memory=customer_memory,
    )


def fallback_report_narrative(metrics: dict, risk_top: list[dict]) -> ReportNarrative:
    """LLM 不可用时的日报降级文案，保证报表任务可稳定落库。"""
    high_risk_count = metrics.get("high_risk_customers", 0)
    pending_approvals = metrics.get("pending_approvals", 0)
    overdue_tasks = metrics.get("overdue_tasks", 0)
    open_deal_amount = metrics.get("open_deal_amount", 0)
    risk_names = "、".join(item.get("customer_name") or item.get("customer_id", "") for item in risk_top[:3]) or "暂无"

    summary = (
        f"今日销售运营共覆盖 {metrics.get('active_customers', 0)} 个在跟客户，"
        f"开放商机 {metrics.get('open_deals', 0)} 个，开放商机金额约 {open_deal_amount} 元。"
        f"当前中高风险客户 {metrics.get('medium_risk_customers', 0) + high_risk_count} 个，"
        f"其中高风险 {high_risk_count} 个；待审批 AI 任务 {pending_approvals} 条，"
        f"逾期任务 {overdue_tasks} 条。"
    )

    suggestions = []
    if high_risk_count:
        suggestions.append(f"优先处理高风险客户：{risk_names}，先由主管确认是否需要介入。")
    if pending_approvals:
        suggestions.append(f"尽快完成 {pending_approvals} 条待审批 AI 任务，避免建议停留在草稿状态。")
    if overdue_tasks:
        suggestions.append(f"清理 {overdue_tasks} 条逾期任务，先确认是否仍有跟进价值，再更新下一步动作。")
    if not suggestions:
        suggestions.append("当前经营风险整体可控，建议保持稳定跟进节奏，并持续补齐下一次跟进时间。")

    return ReportNarrative(summary=summary, suggestions=" ".join(suggestions))


def generate_business_report_narrative(metrics: dict, risk_top: list[dict]) -> ReportNarrative:
    """生成经营日报摘要和建议；LLM 失败时自动降级为规则模板。"""
    system_prompt = (
        "你是 InsightPilot 的企业运营参谋。"
        "请基于经营指标和高风险客户列表生成简洁、可执行的经营日报。"
        "不要编造未提供的数据，不要直接创建任务，只能提出建议。"
    )
    user_message = json.dumps(
        {
            "metrics": metrics,
            "risk_top": risk_top,
            "writing_rules": [
                "摘要控制在 150 字以内",
                "建议要可执行，优先提醒审批、风险客户和逾期任务",
                "不要输出 Markdown",
            ],
        },
        ensure_ascii=False,
        default=str,
    )
    narrative = structured_complete(system_prompt, user_message, ReportNarrative)
    return narrative or fallback_report_narrative(metrics, risk_top)
