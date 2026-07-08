import json
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.modules.memory.conversation_fact_service import CONVERSATION_FACT_SOURCE_TABLE
from app.shared.ids import new_id

ATOMIC_MEMORY_TYPE_WORLD = "world"
ATOMIC_MEMORY_TYPE_EXPERIENCE = "experience"
ATOMIC_MEMORY_TYPE_OPINION = "opinion"
ATOMIC_MEMORY_TYPE_OBSERVATION = "observation"


def _loads_json(value: Any) -> dict[str, Any] | list[Any]:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _dumps_json(value: dict[str, Any] | list[Any]) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _iso_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value in (None, ""):
        return None
    return str(value)


def _join_non_empty_text(parts: list[str], separator: str = "；") -> str:
    return separator.join(part for part in parts if part).strip()


def _normalize_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(confidence, 1.0))


def _normalize_datetime_value(value: Any) -> Any:
    return value if value not in ("", None) else None


def _build_atomic_memory_item(
    *,
    memory_type: str,
    title: str,
    content: str,
    source_table: str,
    source_id: str | None,
    source_run_id: str | None = None,
    occurred_at: Any = None,
    confidence: float | None = None,
    evidence_refs: list[str] | None = None,
    entity_keys: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return None
    return {
        "memory_type": memory_type,
        "title": str(title or "").strip() or None,
        "content": normalized_content,
        "source_table": source_table,
        "source_id": source_id,
        "source_run_id": source_run_id,
        "occurred_at": _normalize_datetime_value(occurred_at),
        "confidence": _normalize_confidence(confidence),
        "evidence_refs": [item for item in (evidence_refs or []) if item],
        "entity_keys": [item for item in (entity_keys or []) if item],
        "metadata_json": metadata or {},
    }


def _build_risk_opinion_confidence(risk_score: Any) -> float:
    try:
        numeric_score = float(risk_score or 0)
    except (TypeError, ValueError):
        numeric_score = 0.0
    # 中文注释：风险快照天然带有分值，第一版 opinion 直接按分值做一个可解释的置信度映射。
    return max(0.55, min(numeric_score / 100.0, 0.95))


def _build_review_confidence(evidence_count: int) -> float:
    # 中文注释：Review 结论没有原生置信度，先按证据数量给一个保守经验值，避免伪精确。
    return max(0.6, min(0.75 + evidence_count * 0.03, 0.9))


def load_customer_memory_map(db: Session, tenant_id: str, customer_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not customer_ids:
        return {}

    rows = db.execute(
        text(
            """
            SELECT memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
            FROM customer_memory
            WHERE tenant_id = :tenant_id
              AND memory_scope = 'customer'
              AND customer_id IN :customer_ids
            """
        ).bindparams(bindparam("customer_ids", expanding=True)),
        {"tenant_id": tenant_id, "customer_ids": customer_ids},
    ).mappings().all()

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["summary_json"] = _loads_json(item.get("summary_json")) or {}
        result[item["customer_id"]] = item
    return result


def _build_customer_memory_summary_text(summary_json: dict[str, Any]) -> str:
    profile = summary_json.get("profile", {})
    risk_state = summary_json.get("risk_state", {})
    approval_state = summary_json.get("approval_state", {})
    task_state = summary_json.get("task_state", {})
    follow_up_state = summary_json.get("follow_up_state", {})
    deal_state = summary_json.get("deal_state", {})
    report_state = summary_json.get("report_state", {})
    agent_state = summary_json.get("agent_state", {})

    parts: list[str] = []
    customer_name = profile.get("customer_name") or profile.get("customer_id") or "该客户"
    parts.append(
        f"{customer_name} 当前阶段为 {profile.get('lifecycle_stage', 'unknown')}，"
        f"意向等级 {profile.get('intent_level', 'unknown')}，"
        f"最近情绪 {profile.get('last_sentiment', 'unknown')}。"
    )

    if profile.get("competitor_involved"):
        parts.append("客户当前存在竞品介入，需要优先关注异议处理和差异化价值。")

    if risk_state.get("latest_risk_level"):
        parts.append(
            f"最近风险等级 {risk_state.get('latest_risk_level')}，"
            f"风险分 {risk_state.get('latest_risk_score', 'unknown')}。"
        )

    if approval_state.get("pending_count"):
        parts.append(f"当前仍有 {approval_state['pending_count']} 条待审批动作，避免重复创建审批。")
    elif approval_state.get("latest_status"):
        parts.append(f"最近一次审批结果为 {approval_state['latest_status']}。")

    if task_state.get("active_count"):
        parts.append(f"客户当前有 {task_state['active_count']} 条执行中任务，建议先确认存量动作效果。")

    if follow_up_state.get("latest_follow_up_type") or follow_up_state.get("latest_follow_up_at"):
        parts.append(
            f"最近一次跟进方式为 {follow_up_state.get('latest_follow_up_type', 'unknown')}，"
            f"时间 {follow_up_state.get('latest_follow_up_at', 'unknown')}。"
        )

    if deal_state.get("latest_stage"):
        parts.append(
            f"最近商机阶段 {deal_state.get('latest_stage')}，"
            f"报价金额 {deal_state.get('latest_quote_amount', 'unknown')}。"
        )

    if report_state.get("latest_report_summary"):
        parts.append(f"最近经营报告摘要：{str(report_state['latest_report_summary'])[:120]}")

    if agent_state.get("latest_review_summary"):
        parts.append(f"最近一次 Agent 复核结论：{agent_state['latest_review_summary']}")

    profile_tags = summary_json.get("profile_tags") or {}
    if profile_tags:
        tag_text = "，".join(str(value) for value in profile_tags.values() if value)
        if tag_text:
            parts.append(f"画像标签：{tag_text}。")

    return "\n".join(part for part in parts if part).strip()


def _build_profile_tags(summary_json: dict[str, Any]) -> dict[str, str]:
    """生成客户画像结构化标签，供画像 Agent 和对话直接读取。"""
    profile = summary_json.get("profile", {})
    risk_state = summary_json.get("risk_state", {})
    follow_up_state = summary_json.get("follow_up_state", {})
    task_state = summary_json.get("task_state", {})
    deal_state = summary_json.get("deal_state", {})

    risk_score = risk_state.get("latest_risk_score") or 0
    risk_level = risk_state.get("latest_risk_level") or "unknown"
    intent_level = profile.get("intent_level") or "unknown"
    lifecycle_stage = profile.get("lifecycle_stage") or "unknown"
    customer_level = profile.get("customer_level") or "unknown"
    follow_up_count = int(follow_up_state.get("count") or 0)
    active_task_count = int(task_state.get("active_count") or 0)

    return {
        "lifecycle_tag": f"阶段:{lifecycle_stage}",
        "intent_tag": f"意向:{intent_level}",
        "value_tag": f"客户等级:{customer_level}",
        "risk_tag": f"风险:{risk_level}/{risk_score}",
        "engagement_tag": "互动:活跃" if follow_up_count >= 3 else "互动:待激活",
        "execution_tag": "执行:有未完成任务" if active_task_count else "执行:暂无未完成任务",
        "competition_tag": "竞品:已介入" if profile.get("competitor_involved") else "竞品:未标记",
        "deal_tag": f"商机:{deal_state.get('latest_stage') or 'unknown'}",
        "quote_tag": "报价:已报价" if deal_state.get("latest_quote_amount") else "报价:未标记",
    }


def _build_customer_atomic_memories(
    *,
    customer: dict[str, Any],
    risk_rows: list[dict[str, Any]],
    approval_rows: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    deal_rows: list[dict[str, Any]],
    follow_up_rows: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
    summary_json: dict[str, Any],
    summary_text: str,
    source_run_id: str,
    runtime_context: dict[str, Any],
    compiled_at: datetime,
) -> list[dict[str, Any]]:
    customer_id = str(customer["customer_id"])
    owner_user_id = str(customer.get("owner_user_id") or "")
    base_entity_keys = [customer_id, owner_user_id]
    items: list[dict[str, Any]] = []

    customer_fact = _build_atomic_memory_item(
        memory_type=ATOMIC_MEMORY_TYPE_WORLD,
        title="客户画像事实",
        content=_join_non_empty_text(
            [
                f"客户 {customer.get('customer_name') or customer_id}",
                f"当前阶段 {customer.get('lifecycle_stage') or 'unknown'}",
                f"意向等级 {customer.get('intent_level') or 'unknown'}",
                f"客户等级 {customer.get('customer_level') or 'unknown'}",
                f"行业 {customer.get('industry') or 'unknown'}",
                f"区域 {customer.get('region') or 'unknown'}",
                f"来源 {customer.get('source') or 'unknown'}",
                f"企业规模 {customer.get('company_size') or 'unknown'}",
                f"预算区间 {customer.get('budget_min') or 'unknown'}-{customer.get('budget_max') or 'unknown'}",
                f"决策人状态 {customer.get('decision_maker_status') or 'unknown'}",
                "存在竞品介入" if customer.get("competitor_involved") else "未标记竞品介入",
                f"最近情绪 {customer.get('last_sentiment') or 'unknown'}",
                f"备注 {customer.get('remark')}" if customer.get("remark") else "",
            ]
        ),
        source_table="crm_customer",
        source_id=customer_id,
        occurred_at=customer.get("updated_at"),
        evidence_refs=[f"crm_customer:{customer_id}"],
        entity_keys=base_entity_keys,
        metadata={
            "memory_scope": "customer",
            "fact_subtype": "customer_profile",
            "profile_tags": summary_json.get("profile_tags") or {},
        },
    )
    if customer_fact:
        items.append(customer_fact)

    for row in risk_rows:
        risk_snapshot_id = str(row.get("risk_snapshot_id") or "")
        risk_fact = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_WORLD,
            title="风险快照事实",
            content=_join_non_empty_text(
                [
                    f"风险等级 {row.get('risk_level') or 'unknown'}",
                    f"风险分 {row.get('risk_score') or 'unknown'}",
                    f"状态 {row.get('status') or 'unknown'}",
                ]
            ),
            source_table="customer_risk_snapshot",
            source_id=risk_snapshot_id or None,
            occurred_at=row.get("created_at"),
            evidence_refs=[f"customer_risk_snapshot:{risk_snapshot_id}"] if risk_snapshot_id else [],
            entity_keys=base_entity_keys,
            metadata={"fact_subtype": "risk_snapshot"},
        )
        if risk_fact:
            items.append(risk_fact)

        if row.get("llm_reason") or row.get("llm_suggestion"):
            opinion_item = _build_atomic_memory_item(
                memory_type=ATOMIC_MEMORY_TYPE_OPINION,
                title="风险判断",
                content=_join_non_empty_text(
                    [
                        f"系统判断当前风险等级为 {row.get('risk_level') or 'unknown'} / {row.get('risk_score') or 'unknown'} 分",
                        f"原因 {row.get('llm_reason')}" if row.get("llm_reason") else "",
                        f"建议 {row.get('llm_suggestion')}" if row.get("llm_suggestion") else "",
                    ]
                ),
                source_table="customer_risk_snapshot",
                source_id=risk_snapshot_id or None,
                occurred_at=row.get("created_at"),
                confidence=_build_risk_opinion_confidence(row.get("risk_score")),
                evidence_refs=[f"customer_risk_snapshot:{risk_snapshot_id}"] if risk_snapshot_id else [],
                entity_keys=base_entity_keys,
                metadata={"opinion_subtype": "risk_assessment"},
            )
            if opinion_item:
                items.append(opinion_item)

    for row in approval_rows:
        approval_id = str(row.get("approval_id") or "")
        approval_fact = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_WORLD,
            title="审批事实",
            content=_join_non_empty_text(
                [
                    f"审批 {approval_id or 'unknown'}",
                    f"状态 {row.get('status') or 'unknown'}",
                    f"审核意见 {row.get('review_comment')}" if row.get("review_comment") else "",
                ]
            ),
            source_table="approval_record",
            source_id=approval_id or None,
            occurred_at=row.get("reviewed_at") or row.get("created_at"),
            evidence_refs=[f"approval_record:{approval_id}"] if approval_id else [],
            entity_keys=base_entity_keys,
            metadata={"fact_subtype": "approval"},
        )
        if approval_fact:
            items.append(approval_fact)

    for row in task_rows:
        task_id = str(row.get("task_id") or "")
        task_fact = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_WORLD,
            title="任务事实",
            content=_join_non_empty_text(
                [
                    f"任务 {row.get('title') or task_id or 'unknown'}",
                    f"优先级 {row.get('priority') or 'unknown'}",
                    f"状态 {row.get('status') or 'unknown'}",
                    f"结果 {row.get('result_note')}" if row.get("result_note") else "",
                ]
            ),
            source_table="sales_task",
            source_id=task_id or None,
            occurred_at=row.get("completed_at") or row.get("due_at") or row.get("created_at"),
            evidence_refs=[f"sales_task:{task_id}"] if task_id else [],
            entity_keys=base_entity_keys,
            metadata={"fact_subtype": "task"},
        )
        if task_fact:
            items.append(task_fact)

    for row in deal_rows:
        deal_id = str(row.get("deal_id") or "")
        deal_fact = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_WORLD,
            title="商机事实",
            content=_join_non_empty_text(
                [
                    f"商机 {row.get('deal_name') or deal_id or 'unknown'}",
                    f"阶段 {row.get('stage') or 'unknown'}",
                    f"金额 {row.get('amount') or 'unknown'}",
                    f"报价 {row.get('quote_amount') or 'unknown'}",
                    f"成交状态 {row.get('close_result') or 'unknown'}",
                ]
            ),
            source_table="crm_deal",
            source_id=deal_id or None,
            occurred_at=row.get("updated_at") or row.get("quoted_at"),
            evidence_refs=[f"crm_deal:{deal_id}"] if deal_id else [],
            entity_keys=base_entity_keys + ([deal_id] if deal_id else []),
            metadata={"fact_subtype": "deal"},
        )
        if deal_fact:
            items.append(deal_fact)

    for row in follow_up_rows:
        follow_up_id = str(row.get("follow_up_id") or "")
        follow_up_fact = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_WORLD,
            title="跟进事实",
            content=_join_non_empty_text(
                [
                    f"跟进方式 {row.get('follow_up_type') or 'unknown'}",
                    f"沟通内容 {row.get('content')}" if row.get("content") else "",
                    f"客户反馈 {row.get('customer_feedback')}" if row.get("customer_feedback") else "",
                    f"客户情绪 {row.get('sentiment') or 'unknown'}",
                    f"下一步 {row.get('next_action')}" if row.get("next_action") else "",
                ]
            ),
            source_table="crm_follow_up_record",
            source_id=follow_up_id or None,
            occurred_at=row.get("occurred_at"),
            evidence_refs=[f"crm_follow_up_record:{follow_up_id}"] if follow_up_id else [],
            entity_keys=base_entity_keys,
            metadata={"fact_subtype": "follow_up"},
        )
        if follow_up_fact:
            items.append(follow_up_fact)

    for row in report_rows:
        report_id = str(row.get("report_id") or "")
        report_fact = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_WORLD,
            title="经营报告事实",
            content=_join_non_empty_text(
                [
                    f"报告类型 {row.get('report_type') or 'unknown'}",
                    f"报告日期 {row.get('report_date') or 'unknown'}",
                    f"摘要 {row.get('summary')}" if row.get("summary") else "",
                ]
            ),
            source_table="business_report",
            source_id=report_id or None,
            occurred_at=row.get("report_date") or row.get("created_at"),
            evidence_refs=[f"business_report:{report_id}"] if report_id else [],
            entity_keys=base_entity_keys,
            metadata={"fact_subtype": "business_report"},
        )
        if report_fact:
            items.append(report_fact)

        if row.get("summary") or row.get("suggestions"):
            report_opinion = _build_atomic_memory_item(
                memory_type=ATOMIC_MEMORY_TYPE_OPINION,
                title="经营报告判断",
                content=_join_non_empty_text(
                    [
                        f"报告结论 {row.get('summary')}" if row.get("summary") else "",
                        f"报告建议 {row.get('suggestions')}" if row.get("suggestions") else "",
                    ]
                ),
                source_table="business_report",
                source_id=report_id or None,
                occurred_at=row.get("report_date") or row.get("created_at"),
                confidence=0.72,
                evidence_refs=[f"business_report:{report_id}"] if report_id else [],
                entity_keys=base_entity_keys,
                metadata={"opinion_subtype": "report_summary"},
            )
            if report_opinion:
                items.append(report_opinion)

    review_context = runtime_context.get("review", {}) if isinstance(runtime_context.get("review"), dict) else {}
    evidence_used = [str(item) for item in review_context.get("evidence_used", []) if item]
    if review_context.get("summary") or review_context.get("review_note"):
        review_opinion = _build_atomic_memory_item(
            memory_type=ATOMIC_MEMORY_TYPE_OPINION,
            title="Agent 复核判断",
            content=_join_non_empty_text(
                [
                    f"复核结论 {review_context.get('summary')}" if review_context.get("summary") else "",
                    f"复核备注 {review_context.get('review_note')}" if review_context.get("review_note") else "",
                ]
            ),
            source_table="agent_run",
            source_id=source_run_id or None,
            source_run_id=source_run_id,
            occurred_at=compiled_at,
            confidence=_build_review_confidence(len(evidence_used)),
            evidence_refs=evidence_used or ([f"agent_run:{source_run_id}"] if source_run_id else []),
            entity_keys=base_entity_keys,
            metadata={"opinion_subtype": "agent_review"},
        )
        if review_opinion:
            items.append(review_opinion)

    advice_context = runtime_context.get("advice", {}) if isinstance(runtime_context.get("advice"), dict) else {}
    created_context = runtime_context.get("created", {}) if isinstance(runtime_context.get("created"), dict) else {}
    tool_names = [
        str(item.get("tool_name"))
        for item in runtime_context.get("tool_executions", [])
        if isinstance(item, dict) and item.get("tool_name")
    ]
    experience_item = _build_atomic_memory_item(
        memory_type=ATOMIC_MEMORY_TYPE_EXPERIENCE,
        title="Agent 执行动作",
        content=_join_non_empty_text(
            [
                f"本轮建议任务 {advice_context.get('task_title')}" if advice_context.get("task_title") else "",
                f"建议优先级 {advice_context.get('priority')}" if advice_context.get("priority") else "",
                f"已创建审批 {created_context.get('approval_id')}" if created_context.get("approval_id") else "",
                f"使用工具 {', '.join(tool_names)}" if tool_names else "",
            ]
        ),
        source_table="agent_run",
        source_id=source_run_id or None,
        source_run_id=source_run_id,
        occurred_at=compiled_at,
        evidence_refs=[f"agent_run:{source_run_id}"] if source_run_id else [],
        entity_keys=base_entity_keys,
        metadata={"experience_subtype": "agent_execution"},
    )
    if experience_item:
        items.append(experience_item)

    observation_item = _build_atomic_memory_item(
        memory_type=ATOMIC_MEMORY_TYPE_OBSERVATION,
        title="客户长期总结",
        content=summary_text,
        source_table="customer_memory",
        source_id=customer_id,
        source_run_id=source_run_id,
        occurred_at=compiled_at,
        evidence_refs=[f"customer_memory:{customer_id}"],
        entity_keys=base_entity_keys,
        metadata={
            "observation_subtype": "compiled_summary",
            "profile_tags": summary_json.get("profile_tags") or {},
        },
    )
    if observation_item:
        items.append(observation_item)

    return items


def build_customer_memory_snapshot(
    db: Session,
    *,
    tenant_id: str,
    customer_id: str,
    source_run_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    runtime_context = runtime_context or {}
    customer = db.execute(
        text(
            """
            SELECT customer_id, customer_name, owner_user_id, industry, region, source,
                   lifecycle_stage, intent_level, customer_level, company_size, budget_min, budget_max,
                   expected_purchase_at, decision_maker_status, competitor_involved, last_sentiment,
                   next_follow_up_at, last_follow_up_at, lost_reason, remark, updated_at
            FROM crm_customer
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().first()
    if not customer:
        return None

    risk_rows = db.execute(
        text(
            """
            SELECT risk_snapshot_id, deal_id, risk_score, risk_level, llm_reason, llm_suggestion, status, created_at
            FROM customer_risk_snapshot
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 3
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    approval_rows = db.execute(
        text(
            """
            SELECT approval_id, status, review_comment, reviewed_at, created_at
            FROM approval_record
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    task_rows = db.execute(
        text(
            """
            SELECT task_id, title, priority, status, due_at, completed_at, result_note, created_at
            FROM sales_task
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    deal_rows = db.execute(
        text(
            """
            SELECT deal_id, deal_name, stage, amount, quote_amount, quoted_at,
                   expected_close_at, close_result, updated_at
            FROM crm_deal
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY updated_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    follow_up_rows = db.execute(
        text(
            """
            SELECT follow_up_id, follow_up_type, content, sentiment, customer_feedback,
                   next_action, next_follow_up_at, occurred_at
            FROM crm_follow_up_record
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY occurred_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    report_rows = db.execute(
        text(
            """
            SELECT report_id, report_type, report_date, summary, suggestions, created_at
            FROM business_report
            WHERE tenant_id = :tenant_id
              AND CAST(risk_top_json AS CHAR) LIKE :customer_pattern
            ORDER BY report_date DESC, created_at DESC
            LIMIT 3
            """
        ),
        {"tenant_id": tenant_id, "customer_pattern": f"%{customer_id}%"},
    ).mappings().all()

    latest_risk = dict(risk_rows[0]) if risk_rows else {}
    latest_approval = dict(approval_rows[0]) if approval_rows else {}
    latest_task = dict(task_rows[0]) if task_rows else {}
    latest_deal = dict(deal_rows[0]) if deal_rows else {}
    latest_follow_up = dict(follow_up_rows[0]) if follow_up_rows else {}
    latest_report = dict(report_rows[0]) if report_rows else {}

    pending_approvals = sum(1 for item in approval_rows if item["status"] == "pending")
    active_tasks = sum(1 for item in task_rows if item["status"] in {"pending", "in_progress"})
    high_risk_count = sum(1 for item in risk_rows if item["risk_level"] == "high")
    medium_or_high_risk_count = sum(1 for item in risk_rows if item["risk_level"] in {"medium", "high"})
    compiled_at = datetime.now()

    summary_json = {
        "profile": {
            "customer_id": customer["customer_id"],
            "customer_name": customer.get("customer_name"),
            "owner_user_id": customer.get("owner_user_id"),
            "industry": customer.get("industry"),
            "region": customer.get("region"),
            "source": customer.get("source"),
            "lifecycle_stage": customer.get("lifecycle_stage"),
            "intent_level": customer.get("intent_level"),
            "customer_level": customer.get("customer_level"),
            "company_size": customer.get("company_size"),
            "budget_min": customer.get("budget_min"),
            "budget_max": customer.get("budget_max"),
            "expected_purchase_at": _iso_datetime(customer.get("expected_purchase_at")),
            "decision_maker_status": customer.get("decision_maker_status"),
            "competitor_involved": bool(customer.get("competitor_involved")),
            "last_sentiment": customer.get("last_sentiment"),
            "next_follow_up_at": _iso_datetime(customer.get("next_follow_up_at")),
            "last_follow_up_at": _iso_datetime(customer.get("last_follow_up_at")),
            "lost_reason": customer.get("lost_reason"),
            "remark": customer.get("remark"),
            "customer_updated_at": _iso_datetime(customer.get("updated_at")),
        },
        "risk_state": {
            "latest_risk_snapshot_id": latest_risk.get("risk_snapshot_id"),
            "latest_risk_level": latest_risk.get("risk_level"),
            "latest_risk_score": latest_risk.get("risk_score"),
            "latest_reason": latest_risk.get("llm_reason"),
            "latest_suggestion": latest_risk.get("llm_suggestion"),
            "recent_high_risk_count": high_risk_count,
            "recent_medium_or_high_risk_count": medium_or_high_risk_count,
            "latest_risk_created_at": _iso_datetime(latest_risk.get("created_at")),
        },
        "approval_state": {
            "total_count": len(approval_rows),
            "pending_count": pending_approvals,
            "latest_approval_id": latest_approval.get("approval_id"),
            "latest_status": latest_approval.get("status"),
            "latest_review_comment": latest_approval.get("review_comment"),
            "latest_reviewed_at": _iso_datetime(latest_approval.get("reviewed_at")),
        },
        "task_state": {
            "total_count": len(task_rows),
            "active_count": active_tasks,
            "latest_task_id": latest_task.get("task_id"),
            "latest_task_title": latest_task.get("title"),
            "latest_task_status": latest_task.get("status"),
            "latest_task_result_note": latest_task.get("result_note"),
            "latest_due_at": _iso_datetime(latest_task.get("due_at")),
        },
        "deal_state": {
            "total_count": len(deal_rows),
            "latest_deal_id": latest_deal.get("deal_id"),
            "latest_deal_name": latest_deal.get("deal_name"),
            "latest_stage": latest_deal.get("stage"),
            "latest_amount": latest_deal.get("amount"),
            "latest_quote_amount": latest_deal.get("quote_amount"),
            "latest_quoted_at": _iso_datetime(latest_deal.get("quoted_at")),
            "latest_expected_close_at": _iso_datetime(latest_deal.get("expected_close_at")),
            "latest_close_result": latest_deal.get("close_result"),
        },
        "follow_up_state": {
            "count": len(follow_up_rows),
            "latest_follow_up_id": latest_follow_up.get("follow_up_id"),
            "latest_follow_up_type": latest_follow_up.get("follow_up_type"),
            "latest_sentiment": latest_follow_up.get("sentiment"),
            "latest_next_action": latest_follow_up.get("next_action"),
            "latest_follow_up_at": _iso_datetime(latest_follow_up.get("occurred_at")),
        },
        "report_state": {
            "report_count": len(report_rows),
            "latest_report_id": latest_report.get("report_id"),
            "latest_report_type": latest_report.get("report_type"),
            "latest_report_date": _iso_datetime(latest_report.get("report_date")),
            "latest_report_summary": latest_report.get("summary"),
            "latest_report_suggestions": latest_report.get("suggestions"),
        },
        "agent_state": {
            "source_run_id": source_run_id,
            "latest_review_summary": runtime_context.get("review", {}).get("summary"),
            "latest_review_note": runtime_context.get("review", {}).get("review_note"),
            "latest_evidence_used": list(runtime_context.get("review", {}).get("evidence_used", [])),
            "latest_tool_names": [
                item.get("tool_name")
                for item in runtime_context.get("tool_executions", [])
                if isinstance(item, dict) and item.get("tool_name")
            ],
            "latest_advice_title": runtime_context.get("advice", {}).get("task_title"),
            "latest_advice_priority": runtime_context.get("advice", {}).get("priority"),
            "latest_created_approval_id": runtime_context.get("created", {}).get("approval_id"),
        },
    }
    summary_json["profile_tags"] = _build_profile_tags(summary_json)
    summary_text = _build_customer_memory_summary_text(summary_json)
    atomic_memories = _build_customer_atomic_memories(
        customer=dict(customer),
        risk_rows=[dict(item) for item in risk_rows],
        approval_rows=[dict(item) for item in approval_rows],
        task_rows=[dict(item) for item in task_rows],
        deal_rows=[dict(item) for item in deal_rows],
        follow_up_rows=[dict(item) for item in follow_up_rows],
        report_rows=[dict(item) for item in report_rows],
        summary_json=summary_json,
        summary_text=summary_text,
        source_run_id=source_run_id,
        runtime_context=runtime_context,
        compiled_at=compiled_at,
    )
    summary_json["memory_layers"] = {
        "world_count": sum(1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_WORLD),
        "experience_count": sum(1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_EXPERIENCE),
        "opinion_count": sum(1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_OPINION),
        "observation_count": sum(1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_OBSERVATION),
    }
    return {
        "customer_id": customer_id,
        "memory_scope": "customer",
        "summary_text": summary_text,
        "summary_json": summary_json,
        "source_run_id": source_run_id,
        "last_compiled_at": compiled_at,
        "atomic_memories": atomic_memories,
    }


def _memory_changed_fields(existing: dict[str, Any] | None, snapshot: dict[str, Any]) -> list[str]:
    if not existing:
        return ["summary_text", "summary_json", "source_run_id", "last_compiled_at"]

    changed: list[str] = []
    existing_json = _loads_json(existing.get("summary_json"))
    if existing.get("summary_text") != snapshot.get("summary_text"):
        changed.append("summary_text")
    if existing_json != snapshot.get("summary_json"):
        changed.append("summary_json")
    if existing.get("source_run_id") != snapshot.get("source_run_id"):
        changed.append("source_run_id")
    return changed


def _insert_memory_update_trace(
    db: Session,
    *,
    tenant_id: str,
    memory_id: str,
    memory_snapshot: dict[str, Any],
    update_type: str,
    changed_fields: list[str],
) -> dict[str, Any]:
    trace_id = new_id("memtrace")
    summary_json = memory_snapshot.get("summary_json") or {}
    profile_tags = summary_json.get("profile_tags") if isinstance(summary_json, dict) else {}
    trace_payload = {
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "memory_id": memory_id,
        "customer_id": memory_snapshot["customer_id"],
        "memory_scope": memory_snapshot["memory_scope"],
        "update_type": update_type,
        "source_type": "agent_run" if memory_snapshot.get("source_run_id") else "manual",
        "source_run_id": memory_snapshot.get("source_run_id"),
        "changed_fields_json": _dumps_json(changed_fields),
        "summary_preview": str(memory_snapshot.get("summary_text") or "")[:500],
        "profile_tags_json": _dumps_json(profile_tags if isinstance(profile_tags, dict) else {}),
        "metadata_json": _dumps_json(
            {
                "compiled_at": _iso_datetime(memory_snapshot.get("last_compiled_at")),
                "summary_json_keys": sorted(summary_json.keys()) if isinstance(summary_json, dict) else [],
                "atomic_memory_count": len(memory_snapshot.get("atomic_memories") or []),
            }
        ),
    }
    db.execute(
        text(
            """
            INSERT INTO memory_update_trace (
              tenant_id, trace_id, memory_id, customer_id, memory_scope, update_type,
              source_type, source_run_id, changed_fields_json, summary_preview,
              profile_tags_json, metadata_json
            )
            VALUES (
              :tenant_id, :trace_id, :memory_id, :customer_id, :memory_scope, :update_type,
              :source_type, :source_run_id, :changed_fields_json, :summary_preview,
              :profile_tags_json, :metadata_json
            )
            """
        ),
        trace_payload,
    )
    return {
        "trace_id": trace_id,
        "update_type": update_type,
        "changed_fields": changed_fields,
    }


def _replace_customer_atomic_memories(
    db: Session,
    *,
    tenant_id: str,
    memory_id: str,
    memory_snapshot: dict[str, Any],
) -> dict[str, Any]:
    customer_id = memory_snapshot["customer_id"]
    memory_scope = memory_snapshot["memory_scope"]
    atomic_memories = list(memory_snapshot.get("atomic_memories") or [])
    db.execute(
        text(
            """
            DELETE FROM customer_memory_atomic
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
              AND memory_scope = :memory_scope
              AND source_table <> :conversation_source_table
            """
        ),
        {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "memory_scope": memory_scope,
            "conversation_source_table": CONVERSATION_FACT_SOURCE_TABLE,
        },
    )

    inserted_count = 0
    for index, item in enumerate(atomic_memories, start=1):
        db.execute(
            text(
                """
                INSERT INTO customer_memory_atomic (
                  tenant_id, atomic_memory_id, memory_id, customer_id, memory_scope, memory_type,
                  order_index, title, content, confidence, occurred_at, source_table, source_id,
                  source_run_id, evidence_refs_json, entity_keys_json, metadata_json
                )
                VALUES (
                  :tenant_id, :atomic_memory_id, :memory_id, :customer_id, :memory_scope, :memory_type,
                  :order_index, :title, :content, :confidence, :occurred_at, :source_table, :source_id,
                  :source_run_id, :evidence_refs_json, :entity_keys_json, :metadata_json
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "atomic_memory_id": new_id("mematom"),
                "memory_id": memory_id,
                "customer_id": customer_id,
                "memory_scope": memory_scope,
                "memory_type": item["memory_type"],
                "order_index": index,
                "title": item.get("title"),
                "content": item["content"],
                "confidence": item.get("confidence"),
                "occurred_at": item.get("occurred_at"),
                "source_table": item["source_table"],
                "source_id": item.get("source_id"),
                "source_run_id": item.get("source_run_id") or memory_snapshot.get("source_run_id"),
                "evidence_refs_json": _dumps_json(item.get("evidence_refs") or []),
                "entity_keys_json": _dumps_json(item.get("entity_keys") or []),
                "metadata_json": _dumps_json(item.get("metadata_json") or {}),
            },
        )
        inserted_count += 1

    return {
        "total_count": inserted_count,
        "by_type": {
            ATOMIC_MEMORY_TYPE_WORLD: sum(1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_WORLD),
            ATOMIC_MEMORY_TYPE_EXPERIENCE: sum(
                1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_EXPERIENCE
            ),
            ATOMIC_MEMORY_TYPE_OPINION: sum(1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_OPINION),
            ATOMIC_MEMORY_TYPE_OBSERVATION: sum(
                1 for item in atomic_memories if item["memory_type"] == ATOMIC_MEMORY_TYPE_OBSERVATION
            ),
        },
    }


def upsert_customer_memory(
    db: Session,
    *,
    tenant_id: str,
    memory_snapshot: dict[str, Any],
) -> dict[str, Any]:
    existing_memory = db.execute(
        text(
            """
            SELECT memory_id, summary_text, summary_json, source_run_id
            FROM customer_memory
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
              AND memory_scope = :memory_scope
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "customer_id": memory_snapshot["customer_id"],
            "memory_scope": memory_snapshot["memory_scope"],
        },
    ).mappings().first()
    existing_memory_item = dict(existing_memory) if existing_memory else None
    existing_memory_id = existing_memory_item.get("memory_id") if existing_memory_item else None
    memory_id = existing_memory_id or new_id("memo")
    update_type = "update" if existing_memory_id else "create"
    changed_fields = _memory_changed_fields(existing_memory_item, memory_snapshot)

    db.execute(
        text(
            """
            INSERT INTO customer_memory (
              tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json,
              source_run_id, last_compiled_at
            )
            VALUES (
              :tenant_id, :memory_id, :customer_id, :memory_scope, :summary_text, :summary_json,
              :source_run_id, :last_compiled_at
            )
            ON DUPLICATE KEY UPDATE
              summary_text = VALUES(summary_text),
              summary_json = VALUES(summary_json),
              source_run_id = VALUES(source_run_id),
              last_compiled_at = VALUES(last_compiled_at)
            """
        ),
        {
            "tenant_id": tenant_id,
            "memory_id": memory_id,
            "customer_id": memory_snapshot["customer_id"],
            "memory_scope": memory_snapshot["memory_scope"],
            "summary_text": memory_snapshot["summary_text"],
            "summary_json": _dumps_json(memory_snapshot["summary_json"]),
            "source_run_id": memory_snapshot["source_run_id"],
            "last_compiled_at": memory_snapshot["last_compiled_at"],
        },
    )
    # 中文注释：summary 层写完以后，同步全量重建原子长期记忆，保证 observation 和底层证据始终一致。
    atomic_refresh = _replace_customer_atomic_memories(
        db,
        tenant_id=tenant_id,
        memory_id=memory_id,
        memory_snapshot=memory_snapshot,
    )
    # 中文注释：记忆正文写入成功后追加审计轨迹，后续治理页可以按客户或 run 追溯每次刷新来源。
    trace = _insert_memory_update_trace(
        db,
        tenant_id=tenant_id,
        memory_id=memory_id,
        memory_snapshot=memory_snapshot,
        update_type=update_type,
        changed_fields=changed_fields,
    )

    return {
        "memory_id": memory_id,
        "customer_id": memory_snapshot["customer_id"],
        "memory_scope": memory_snapshot["memory_scope"],
        "summary_text": memory_snapshot["summary_text"],
        "summary_json": memory_snapshot["summary_json"],
        "source_run_id": memory_snapshot["source_run_id"],
        "last_compiled_at": memory_snapshot["last_compiled_at"].isoformat(),
        "atomic_refresh": atomic_refresh,
        "update_trace": trace,
    }
