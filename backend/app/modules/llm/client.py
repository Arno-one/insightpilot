import json
import logging
from typing import Type

from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class RiskAdvice(BaseModel):
    """客户风险建议的结构化输出，便于直接落库和生成审批草稿。"""

    reason: str = Field(..., description="风险原因说明")
    suggestion: str = Field(..., description="处理建议")
    task_type: str = Field(..., description="任务类型")
    task_title: str = Field(..., description="任务标题")
    priority: str = Field(..., description="任务优先级")
    recommended_script: str = Field(..., description="推荐沟通话术")


class ReportNarrative(BaseModel):
    """经营日报的结构化摘要输出，便于直接写入 business_report。"""

    summary: str = Field(..., description="日报摘要")
    suggestions: str = Field(..., description="经营建议")


def _json_schema_instruction(schema: Type[BaseModel]) -> str:
    """根据 Pydantic Schema 生成简洁 JSON 输出约束。"""
    fields = []
    for name, field in schema.model_fields.items():
        desc = field.description or name
        fields.append(f'  "{name}": "string" // {desc}')
    return "{\n" + ",\n".join(fields) + "\n}"


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


def structured_complete(system_prompt: str, user_message: str, schema: Type[BaseModel]) -> BaseModel | None:
    """调用 DeepSeek 并校验结构化 JSON；失败返回 None，由业务层降级处理。"""
    if not settings.deepseek_api_key:
        logger.warning("未配置 DEEPSEEK_API_KEY，跳过 LLM 调用")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        response = client.chat.completions.create(
            model="deepseek-chat",
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
        raw = response.choices[0].message.content or ""
        data = json.loads(_strip_code_fence(raw))
        return schema.model_validate(data)
    except Exception as exc:
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


def generate_risk_advice(customer: dict, deal: dict | None, risk_result: dict, rag_context: str = "") -> RiskAdvice:
    """生成客户风险解释、建议和任务草稿。"""
    system_prompt = (
        "你是 InsightPilot 的企业运营参谋。"
        "风险分由规则引擎计算，你只能基于规则命中、客户资料和知识库上下文生成解释和建议。"
        "不要声称已经联系客户，不要绕过人工审批。"
    )
    user_message = json.dumps(
        {
            "customer": customer,
            "deal": deal,
            "risk_result": risk_result,
            "rag_context": rag_context,
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
