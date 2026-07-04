import json
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.agent import chat_session_service, conversation_memory_service
from app.modules.crm import service as crm_service
from app.modules.nl2sql import dao as nl2sql_dao


ShortTermSource = Literal["agent_chat", "risk_chat", "nl2sql"]
SOURCE_TYPES: tuple[ShortTermSource, ...] = ("agent_chat", "risk_chat", "nl2sql")


def _loads_metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _standard_session(
    *,
    source_type: ShortTermSource,
    session_id: str,
    title: str,
    status: str,
    user_id: str,
    scope: str | None = None,
    intent: str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    memory_key: str | None = None,
    history_summary: str = "",
    message_count: int = 0,
    last_message_at: Any = None,
    updated_at: Any = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "memory_id": f"{source_type}:{session_id}",
        "session_id": session_id,
        "title": title,
        "status": status,
        "user_id": user_id,
        "scope": scope,
        "intent": intent,
        "related_entity_type": related_entity_type,
        "related_entity_id": related_entity_id,
        "memory_key": memory_key,
        "history_summary": history_summary,
        "message_count": message_count,
        "last_message_at": last_message_at,
        "updated_at": updated_at,
        "metadata_json": metadata_json or {},
    }


def _standard_message(
    *,
    source_type: ShortTermSource,
    session_id: str,
    message_id: str,
    role: str,
    content: str,
    created_at: Any = None,
    intent: str | None = None,
    tool_name: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "memory_id": f"{source_type}:{session_id}",
        "session_id": session_id,
        "message_id": message_id,
        "role": role,
        "content": content,
        "intent": intent,
        "tool_name": tool_name,
        "run_id": run_id,
        "trace_id": trace_id,
        "created_at": created_at,
        "metadata_json": metadata_json or {},
    }


def _agent_session_to_standard(row: dict[str, Any]) -> dict[str, Any]:
    return _standard_session(
        source_type="agent_chat",
        session_id=row["session_id"],
        title=row.get("title") or "Agent 对话",
        status=row.get("status") or "active",
        user_id=row["user_id"],
        scope=row.get("agent_scope"),
        intent=row.get("intent"),
        related_entity_type="customer" if row.get("related_customer_id") else None,
        related_entity_id=row.get("related_customer_id"),
        memory_key=row.get("memory_key"),
        message_count=int(row.get("message_count") or 0),
        last_message_at=row.get("last_message_at"),
        updated_at=row.get("updated_at"),
        metadata_json=_loads_metadata(row.get("context_json")),
    )


def _agent_message_to_standard(row: dict[str, Any]) -> dict[str, Any]:
    return _standard_message(
        source_type="agent_chat",
        session_id=row["session_id"],
        message_id=row["message_id"],
        role=row["role"],
        content=row["content"],
        intent=row.get("intent"),
        tool_name=row.get("tool_name"),
        run_id=row.get("run_id"),
        trace_id=row.get("trace_id"),
        created_at=row.get("created_at"),
        metadata_json=_loads_metadata(row.get("metadata_json")),
    )


def _nl2sql_session_to_standard(row: dict[str, Any]) -> dict[str, Any]:
    return _standard_session(
        source_type="nl2sql",
        session_id=row["session_id"],
        title=row.get("title") or "数据问答会话",
        status=row.get("status") or "active",
        user_id=row["user_id"],
        scope=row.get("data_scope"),
        intent="data_query",
        memory_key=f"nl2sql:{row['tenant_id']}:{row['user_id']}:{row['session_id']}",
        message_count=int(row.get("message_count") or 0),
        last_message_at=row.get("last_message_at"),
        updated_at=row.get("updated_at"),
        metadata_json=_loads_metadata(row.get("context_json")),
    )


def _nl2sql_message_to_standard(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _loads_metadata(row.get("metadata_json"))
    if row.get("query_id"):
        metadata = {**metadata, "query_id": row.get("query_id")}
    return _standard_message(
        source_type="nl2sql",
        session_id=row["session_id"],
        message_id=row["message_id"],
        role=row["role"],
        content=row["content"],
        intent="data_query",
        tool_name="nl2sql.query" if row.get("query_id") else None,
        created_at=row.get("created_at"),
        metadata_json=metadata,
    )


def _risk_session_to_standard(item: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    customer_id = str(item.get("customer_id") or "")
    return _standard_session(
        source_type="risk_chat",
        session_id=customer_id,
        title=str(item.get("title") or item.get("customer_name") or "风险对话"),
        status="active",
        user_id=user_id,
        scope="risk",
        intent="risk_analysis",
        related_entity_type="customer",
        related_entity_id=customer_id,
        memory_key=item.get("session_key"),
        message_count=0,
        last_message_at=item.get("updated_at"),
        updated_at=item.get("updated_at"),
        metadata_json={
            "customer_name": item.get("customer_name"),
            "latest_risk_level": item.get("latest_risk_level"),
            "preview": item.get("preview"),
        },
    )


def _risk_message_to_standard(row: dict[str, Any], *, customer_id: str, index: int) -> dict[str, Any]:
    return _standard_message(
        source_type="risk_chat",
        session_id=customer_id,
        message_id=f"risk_msg_{index + 1}",
        role=str(row.get("role") or "assistant"),
        content=str(row.get("content") or ""),
        intent="risk_analysis",
        created_at=row.get("created_at"),
    )


def list_short_term_sessions(
    db: Session,
    current_user: dict[str, Any],
    *,
    source_type: ShortTermSource | None = None,
    limit: int = 50,
    redis_client=None,
) -> list[dict[str, Any]]:
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]
    max_limit = max(1, min(limit, 100))
    sources = [source_type] if source_type else list(SOURCE_TYPES)
    sessions: list[dict[str, Any]] = []

    if "agent_chat" in sources:
        sessions.extend(
            _agent_session_to_standard(row)
            for row in chat_session_service.list_chat_sessions(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                limit=max_limit,
            )
        )

    if "nl2sql" in sources:
        sessions.extend(
            _nl2sql_session_to_standard(row)
            for row in nl2sql_dao.list_sessions(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                limit=max_limit,
            )
        )

    if "risk_chat" in sources:
        risk_items = conversation_memory_service.list_conversation_sessions(
            tenant_id,
            user_id,
            redis_client=redis_client,
        )
        sessions.extend(_risk_session_to_standard(item, user_id=user_id) for item in risk_items[:max_limit])

    sessions.sort(key=lambda item: str(item.get("last_message_at") or item.get("updated_at") or ""), reverse=True)
    return sessions[:max_limit]


def load_short_term_memory(
    db: Session,
    current_user: dict[str, Any],
    *,
    source_type: ShortTermSource,
    session_id: str,
    limit: int = 100,
    redis_client=None,
) -> dict[str, Any]:
    if source_type not in SOURCE_TYPES:
        raise ValueError("不支持的短期记忆来源")

    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]
    max_limit = max(1, min(limit, 200))

    if source_type == "agent_chat":
        session = chat_session_service.get_chat_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
        messages = chat_session_service.list_chat_messages(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            limit=max_limit,
        )
        return {
            "session": _agent_session_to_standard(session),
            "messages": [_agent_message_to_standard(item) for item in messages],
        }

    if source_type == "nl2sql":
        session = nl2sql_dao.get_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
        messages = nl2sql_dao.list_messages(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id, limit=max_limit)
        return {
            "session": _nl2sql_session_to_standard(session),
            "messages": [_nl2sql_message_to_standard(item) for item in messages],
        }

    memory = conversation_memory_service.load_conversation_memory(
        tenant_id,
        user_id,
        session_id,
        redis_client=redis_client,
    )
    # 中文注释：Risk Chat 的 session_id 采用 customer_id，兼容现有 Redis 会话键。
    session = _standard_session(
        source_type="risk_chat",
        session_id=session_id,
        title="风险对话",
        status="active",
        user_id=user_id,
        scope="risk",
        intent="risk_analysis",
        related_entity_type="customer",
        related_entity_id=session_id,
        memory_key=memory["session_key"],
        history_summary=str(memory.get("history_summary") or ""),
        message_count=len(memory.get("recent_messages") or []),
        last_message_at=memory.get("updated_at"),
        updated_at=memory.get("updated_at"),
        metadata_json={"memory_window": memory.get("memory_window") or {}},
    )
    return {
        "session": session,
        "messages": [
            _risk_message_to_standard(item, customer_id=session_id, index=index)
            for index, item in enumerate(list(memory.get("recent_messages") or [])[-max_limit:])
        ],
    }


def summarize_short_term_memory(
    db: Session,
    current_user: dict[str, Any],
    *,
    redis_client=None,
) -> dict[str, Any]:
    sessions = list_short_term_sessions(db, current_user, limit=100, redis_client=redis_client)
    by_source = {source: 0 for source in SOURCE_TYPES}
    for item in sessions:
        by_source[item["source_type"]] += 1
    return {
        "source_types": list(SOURCE_TYPES),
        "session_count": len(sessions),
        "by_source": by_source,
        "latest_sessions": sessions[:10],
    }


def _load_latest_customer_memory(db: Session, *, tenant_id: str, customer_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT memory_id, customer_id, memory_scope, summary_text, summary_json,
                   source_run_id, last_compiled_at, updated_at
            FROM customer_memory
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
              AND memory_scope = 'customer'
            ORDER BY last_compiled_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().first()
    if not row:
        return {}
    item = dict(row)
    item["summary_json"] = _loads_json(item.get("summary_json"))
    return item


def _trace_row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    changed_fields_raw = item.pop("changed_fields_json", None)
    if isinstance(changed_fields_raw, list):
        changed_fields = changed_fields_raw
    else:
        try:
            parsed_changed_fields = json.loads(changed_fields_raw) if changed_fields_raw else []
        except (TypeError, json.JSONDecodeError):
            parsed_changed_fields = []
        changed_fields = parsed_changed_fields if isinstance(parsed_changed_fields, list) else []
    item["changed_fields"] = changed_fields
    item["profile_tags"] = _loads_json(item.pop("profile_tags_json", None))
    item["metadata_json"] = _loads_json(item.get("metadata_json"))
    item["created_at"] = _iso(item.get("created_at"))
    return item


def list_customer_memory_update_traces(
    db: Session,
    current_user: dict[str, Any],
    *,
    customer_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    crm_service.load_customer_or_404(db, current_user, customer_id)
    rows = db.execute(
        text(
            """
            SELECT trace_id, memory_id, customer_id, memory_scope, update_type, source_type,
                   source_run_id, changed_fields_json, summary_preview, profile_tags_json,
                   metadata_json, created_at
            FROM memory_update_trace
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "customer_id": customer_id,
            "limit": max(1, min(limit, 100)),
        },
    ).mappings().all()
    return [_trace_row_to_item(row) for row in rows]


def _build_recommended_focus(
    *,
    risk_state: dict[str, Any],
    opportunity_state: dict[str, Any],
    follow_up_state: dict[str, Any],
    approval_state: dict[str, Any],
    task_state: dict[str, Any],
) -> list[str]:
    focus: list[str] = []
    if risk_state.get("latest_risk_level") in {"high", "medium"}:
        focus.append("优先处理当前风险，并核对最新风险建议")
    if approval_state.get("pending_count"):
        focus.append("先查看待审批动作，避免重复创建外发或执行任务")
    if task_state.get("active_count"):
        focus.append("跟进未完成任务的执行结果")
    if opportunity_state.get("open_count"):
        focus.append("结合开放商机阶段推进成交动作")
    if not follow_up_state.get("latest_follow_up_at"):
        focus.append("补充最近跟进信息，避免上下文缺口影响 Agent 判断")
    return focus[:5]


def _top_values(items: list[dict[str, Any]], key: str, *, limit: int = 3) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key)
        if value in (None, ""):
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    ]


def _last_text_samples(items: list[dict[str, Any]], key: str, *, limit: int = 3) -> list[str]:
    samples: list[str] = []
    for item in items:
        value = item.get(key)
        if value:
            samples.append(str(value))
        if len(samples) >= limit:
            break
    return samples


def _clip_text(value: Any, max_chars: int) -> str:
    text_value = str(value or "").strip()
    if len(text_value) <= max_chars:
        return text_value
    return f"{text_value[: max(max_chars - 1, 0)]}…"


def _join_non_empty(parts: list[str], separator: str = "；") -> str:
    return separator.join(part for part in parts if part)


def _build_long_term_usage_hints(
    *,
    preference_state: dict[str, Any],
    behavior_state: dict[str, Any],
    long_term_profile: dict[str, Any],
) -> list[str]:
    hints: list[str] = []
    if preference_state.get("preferred_follow_up_type"):
        hints.append(f"优先使用客户历史高频沟通方式：{preference_state['preferred_follow_up_type']}")
    if long_term_profile.get("competitor_involved"):
        hints.append("回复和行动建议需要保留竞品对比、差异化价值与异议处理上下文")
    if behavior_state.get("risk_level_history"):
        hints.append("生成建议前先参考历史风险变化，避免只看最近一次快照")
    if behavior_state.get("task_result_history"):
        hints.append("创建新任务前先检查历史任务结果，避免重复安排无效动作")
    if not hints:
        hints.append("长期记忆样本较少，Agent 应降低确定性表达并优先补充事实")
    return hints[:5]


def _context_section(
    *,
    section_type: str,
    title: str,
    content: str,
    source_refs: list[str],
    priority: int,
) -> dict[str, Any]:
    return {
        "section_type": section_type,
        "title": title,
        "content": content,
        "source_refs": source_refs,
        "priority": priority,
        "char_count": len(content),
    }


def _pack_context_sections(sections: list[dict[str, Any]], *, max_chars: int) -> tuple[list[dict[str, Any]], str, bool]:
    used = 0
    packed: list[dict[str, Any]] = []
    lines: list[str] = []
    overflow = False
    for section in sorted(sections, key=lambda item: item["priority"]):
        header = f"[{section['title']}]"
        content = str(section.get("content") or "")
        block = f"{header}\n{content}"
        remaining = max_chars - used
        if remaining <= len(header) + 8:
            overflow = True
            continue
        if len(block) > remaining:
            overflow = True
            content = _clip_text(content, max(remaining - len(header) - 1, 0))
            block = f"{header}\n{content}"
        packed_section = {**section, "content": content, "char_count": len(content)}
        packed.append(packed_section)
        lines.append(block)
        used += len(block) + 2
    return packed, "\n\n".join(lines), overflow


def load_customer_working_memory(
    db: Session,
    current_user: dict[str, Any],
    *,
    customer_id: str,
) -> dict[str, Any]:
    bundle = crm_service.load_customer_detail_bundle(db, current_user, customer_id)
    customer = bundle["customer"]
    risks = list(bundle.get("risk_snapshots") or [])
    deals = list(bundle.get("deals") or [])
    follow_ups = list(bundle.get("follow_ups") or [])
    approvals = list(bundle.get("approvals") or [])
    tasks = list(bundle.get("tasks") or [])
    latest_memory = _load_latest_customer_memory(
        db,
        tenant_id=current_user["tenant_id"],
        customer_id=customer_id,
    )

    latest_risk = risks[0] if risks else {}
    open_deals = [item for item in deals if item.get("close_result") == "open"]
    latest_deal = deals[0] if deals else {}
    latest_follow_up = follow_ups[0] if follow_ups else {}
    pending_approvals = [item for item in approvals if item.get("status") == "pending"]
    active_tasks = [item for item in tasks if item.get("status") in {"pending", "in_progress"}]

    profile = {
        "customer_id": customer["customer_id"],
        "customer_name": customer["customer_name"],
        "owner_user_id": customer["owner_user_id"],
        "owner_user_name": customer.get("owner_user_name"),
        "lifecycle_stage": customer.get("lifecycle_stage"),
        "intent_level": customer.get("intent_level"),
        "customer_level": customer.get("customer_level"),
        "industry": customer.get("industry"),
        "region": customer.get("region"),
        "competitor_involved": bool(customer.get("competitor_involved")),
        "last_sentiment": customer.get("last_sentiment"),
        "next_follow_up_at": _iso(customer.get("next_follow_up_at")),
        "last_follow_up_at": _iso(customer.get("last_follow_up_at")),
    }
    risk_state = {
        "latest_risk_snapshot_id": latest_risk.get("risk_snapshot_id"),
        "latest_risk_level": latest_risk.get("risk_level"),
        "latest_risk_score": latest_risk.get("risk_score"),
        "latest_reason": latest_risk.get("llm_reason"),
        "latest_suggestion": latest_risk.get("llm_suggestion"),
        "latest_status": latest_risk.get("status"),
        "recent_count": len(risks),
    }
    opportunity_state = {
        "total_count": len(deals),
        "open_count": len(open_deals),
        "latest_deal_id": latest_deal.get("deal_id"),
        "latest_deal_name": latest_deal.get("deal_name"),
        "latest_stage": latest_deal.get("stage"),
        "latest_amount": latest_deal.get("amount"),
        "latest_quote_amount": latest_deal.get("quote_amount"),
        "latest_close_result": latest_deal.get("close_result"),
    }
    follow_up_state = {
        "recent_count": len(follow_ups),
        "latest_follow_up_id": latest_follow_up.get("follow_up_id"),
        "latest_follow_up_type": latest_follow_up.get("follow_up_type"),
        "latest_sentiment": latest_follow_up.get("sentiment"),
        "latest_feedback": latest_follow_up.get("customer_feedback"),
        "latest_next_action": latest_follow_up.get("next_action"),
        "latest_follow_up_at": _iso(latest_follow_up.get("occurred_at")),
        "next_follow_up_at": _iso(latest_follow_up.get("next_follow_up_at") or customer.get("next_follow_up_at")),
    }
    approval_state = {
        "total_count": len(approvals),
        "pending_count": len(pending_approvals),
        "latest_approval_id": approvals[0].get("approval_id") if approvals else None,
        "latest_status": approvals[0].get("status") if approvals else None,
        "latest_review_comment": approvals[0].get("review_comment") if approvals else None,
    }
    task_state = {
        "total_count": len(tasks),
        "active_count": len(active_tasks),
        "latest_task_id": tasks[0].get("task_id") if tasks else None,
        "latest_task_title": tasks[0].get("title") if tasks else None,
        "latest_task_status": tasks[0].get("status") if tasks else None,
        "latest_due_at": _iso(tasks[0].get("due_at")) if tasks else None,
    }
    memory_state = {
        "memory_id": latest_memory.get("memory_id"),
        "summary_text": latest_memory.get("summary_text") or "",
        "summary_json": latest_memory.get("summary_json") or {},
        "source_run_id": latest_memory.get("source_run_id"),
        "last_compiled_at": _iso(latest_memory.get("last_compiled_at")),
    }
    recommended_focus = _build_recommended_focus(
        risk_state=risk_state,
        opportunity_state=opportunity_state,
        follow_up_state=follow_up_state,
        approval_state=approval_state,
        task_state=task_state,
    )

    return {
        "source_type": "customer_working_memory",
        "memory_id": f"customer_working:{customer_id}",
        "customer_id": customer_id,
        "generated_at": datetime.now().isoformat(),
        "profile": profile,
        "risk_state": risk_state,
        "opportunity_state": opportunity_state,
        "follow_up_state": follow_up_state,
        "approval_state": approval_state,
        "task_state": task_state,
        "memory_state": memory_state,
        "recommended_focus": recommended_focus,
        "raw_refs": {
            "risk_snapshot_count": len(risks),
            "deal_count": len(deals),
            "follow_up_count": len(follow_ups),
            "approval_count": len(approvals),
            "task_count": len(tasks),
        },
    }


def load_customer_long_term_memory(
    db: Session,
    current_user: dict[str, Any],
    *,
    customer_id: str,
) -> dict[str, Any]:
    bundle = crm_service.load_customer_detail_bundle(db, current_user, customer_id)
    customer = bundle["customer"]
    risks = list(bundle.get("risk_snapshots") or [])
    deals = list(bundle.get("deals") or [])
    follow_ups = list(bundle.get("follow_ups") or [])
    approvals = list(bundle.get("approvals") or [])
    tasks = list(bundle.get("tasks") or [])
    report_refs = list(bundle.get("report_refs") or [])
    latest_memory = _load_latest_customer_memory(
        db,
        tenant_id=current_user["tenant_id"],
        customer_id=customer_id,
    )
    summary_json = latest_memory.get("summary_json") or {}
    memory_profile = summary_json.get("profile") or {}
    profile_tags = summary_json.get("profile_tags") or {}

    preferred_follow_up_types = _top_values(follow_ups, "follow_up_type")
    preferred_follow_up_type = preferred_follow_up_types[0]["value"] if preferred_follow_up_types else None
    sentiment_history = [
        {
            "follow_up_id": item.get("follow_up_id"),
            "sentiment": item.get("sentiment"),
            "occurred_at": _iso(item.get("occurred_at")),
        }
        for item in follow_ups
        if item.get("sentiment")
    ]
    deal_stage_history = [
        {
            "deal_id": item.get("deal_id"),
            "deal_name": item.get("deal_name"),
            "stage": item.get("stage"),
            "close_result": item.get("close_result"),
            "updated_at": _iso(item.get("updated_at")),
        }
        for item in deals
    ]
    risk_level_history = [
        {
            "risk_snapshot_id": item.get("risk_snapshot_id"),
            "risk_level": item.get("risk_level"),
            "risk_score": item.get("risk_score"),
            "created_at": _iso(item.get("created_at")),
        }
        for item in risks
    ]
    task_result_history = [
        {
            "task_id": item.get("task_id"),
            "title": item.get("title"),
            "status": item.get("status"),
            "result_note": item.get("result_note"),
            "completed_at": _iso(item.get("completed_at")),
        }
        for item in tasks
        if item.get("result_note") or item.get("completed_at") or item.get("status") == "completed"
    ]

    preference_state = {
        "industry": customer.get("industry") or memory_profile.get("industry"),
        "region": customer.get("region") or memory_profile.get("region"),
        "source": customer.get("source"),
        "company_size": customer.get("company_size"),
        "budget_range": {
            "min": customer.get("budget_min"),
            "max": customer.get("budget_max"),
        },
        "expected_purchase_at": _iso(customer.get("expected_purchase_at")),
        "decision_maker_status": customer.get("decision_maker_status"),
        "preferred_follow_up_type": preferred_follow_up_type,
        "preferred_follow_up_types": preferred_follow_up_types,
        # 中文注释：保留最近客户原话/反馈样本，方便 Agent 判断长期偏好时有证据可引用。
        "feedback_samples": _last_text_samples(follow_ups, "customer_feedback"),
        "next_action_samples": _last_text_samples(follow_ups, "next_action"),
    }
    behavior_state = {
        "follow_up_count": len(follow_ups),
        "deal_count": len(deals),
        "risk_snapshot_count": len(risks),
        "approval_count": len(approvals),
        "task_count": len(tasks),
        "report_ref_count": len(report_refs),
        "sentiment_history": sentiment_history[:5],
        "deal_stage_history": deal_stage_history[:5],
        "risk_level_history": risk_level_history[:5],
        "task_result_history": task_result_history[:5],
    }
    long_term_profile = {
        "customer_id": customer["customer_id"],
        "customer_name": customer["customer_name"],
        "owner_user_id": customer["owner_user_id"],
        "owner_user_name": customer.get("owner_user_name"),
        "lifecycle_stage": customer.get("lifecycle_stage") or memory_profile.get("lifecycle_stage"),
        "intent_level": customer.get("intent_level") or memory_profile.get("intent_level"),
        "customer_level": customer.get("customer_level") or memory_profile.get("customer_level"),
        "competitor_involved": bool(customer.get("competitor_involved") or memory_profile.get("competitor_involved")),
        "last_sentiment": customer.get("last_sentiment") or memory_profile.get("last_sentiment"),
        "last_follow_up_at": _iso(customer.get("last_follow_up_at") or memory_profile.get("last_follow_up_at")),
        "next_follow_up_at": _iso(customer.get("next_follow_up_at") or memory_profile.get("next_follow_up_at")),
        "lost_reason": customer.get("lost_reason"),
        "remark": customer.get("remark"),
        "profile_tags": profile_tags,
        "stable_traits": [str(value) for value in profile_tags.values() if value],
    }
    memory_state = {
        "memory_id": latest_memory.get("memory_id"),
        "summary_text": latest_memory.get("summary_text") or "",
        "summary_json": summary_json,
        "source_run_id": latest_memory.get("source_run_id"),
        "last_compiled_at": _iso(latest_memory.get("last_compiled_at")),
    }
    memory_quality = {
        "has_compiled_memory": bool(latest_memory),
        "profile_tag_count": len(profile_tags),
        "behavior_sample_count": len(follow_ups) + len(deals) + len(risks) + len(tasks),
        "has_feedback_samples": bool(preference_state["feedback_samples"]),
    }

    return {
        "source_type": "customer_long_term_memory",
        "memory_id": f"customer_long_term:{customer_id}",
        "customer_id": customer_id,
        "generated_at": datetime.now().isoformat(),
        "long_term_profile": long_term_profile,
        "preference_state": preference_state,
        "behavior_state": behavior_state,
        "memory_state": memory_state,
        "memory_quality": memory_quality,
        "recommended_usage": _build_long_term_usage_hints(
            preference_state=preference_state,
            behavior_state=behavior_state,
            long_term_profile=long_term_profile,
        ),
        "raw_refs": {
            "risk_snapshot_count": len(risks),
            "deal_count": len(deals),
            "follow_up_count": len(follow_ups),
            "approval_count": len(approvals),
            "task_count": len(tasks),
            "report_ref_count": len(report_refs),
        },
    }


def build_customer_context_packet(
    db: Session,
    current_user: dict[str, Any],
    *,
    customer_id: str,
    max_chars: int = 2400,
) -> dict[str, Any]:
    char_budget = max(600, min(max_chars, 6000))
    working = load_customer_working_memory(db, current_user, customer_id=customer_id)
    long_term = load_customer_long_term_memory(db, current_user, customer_id=customer_id)
    profile = working["profile"]
    risk_state = working["risk_state"]
    opportunity_state = working["opportunity_state"]
    follow_up_state = working["follow_up_state"]
    approval_state = working["approval_state"]
    task_state = working["task_state"]
    preference_state = long_term["preference_state"]
    behavior_state = long_term["behavior_state"]
    long_term_profile = long_term["long_term_profile"]
    memory_state = long_term["memory_state"]

    # 中文注释：Context Packet 只保留 Agent 决策所需事实，完整 JSON 仍可通过 Memory API 回查。
    sections = [
        _context_section(
            section_type="customer_profile",
            title="客户画像",
            priority=10,
            source_refs=["crm_customer", "customer_memory"],
            content=_join_non_empty(
                [
                    f"{profile.get('customer_name')}({customer_id})",
                    f"阶段:{long_term_profile.get('lifecycle_stage')}",
                    f"意向:{long_term_profile.get('intent_level')}",
                    f"等级:{long_term_profile.get('customer_level')}",
                    f"行业:{preference_state.get('industry')}",
                    f"区域:{preference_state.get('region')}",
                    "竞品已介入" if long_term_profile.get("competitor_involved") else "",
                    f"标签:{'，'.join(long_term_profile.get('stable_traits') or [])}",
                ]
            ),
        ),
        _context_section(
            section_type="working_memory",
            title="当前状态",
            priority=20,
            source_refs=["crm_detail_bundle"],
            content=_join_non_empty(
                [
                    f"风险:{risk_state.get('latest_risk_level')}/{risk_state.get('latest_risk_score')}",
                    f"风险原因:{risk_state.get('latest_reason')}",
                    f"开放商机:{opportunity_state.get('open_count')}，最近阶段:{opportunity_state.get('latest_stage')}",
                    f"最近跟进:{follow_up_state.get('latest_follow_up_type')}，情绪:{follow_up_state.get('latest_sentiment')}，下一步:{follow_up_state.get('latest_next_action')}",
                    f"待审批:{approval_state.get('pending_count')}，执行中任务:{task_state.get('active_count')}",
                ]
            ),
        ),
        _context_section(
            section_type="long_term_preference",
            title="长期偏好",
            priority=30,
            source_refs=["crm_follow_up_record", "customer_memory"],
            content=_join_non_empty(
                [
                    f"预算:{preference_state.get('budget_range', {}).get('min')}-{preference_state.get('budget_range', {}).get('max')}",
                    f"决策人:{preference_state.get('decision_maker_status')}",
                    f"高频沟通:{preference_state.get('preferred_follow_up_type')}",
                    f"反馈样本:{' / '.join(preference_state.get('feedback_samples') or [])}",
                    f"行动样本:{' / '.join(preference_state.get('next_action_samples') or [])}",
                ]
            ),
        ),
        _context_section(
            section_type="behavior_history",
            title="行为历史",
            priority=40,
            source_refs=["crm_follow_up_record", "crm_deal", "customer_risk_snapshot", "sales_task"],
            content=_join_non_empty(
                [
                    f"跟进:{behavior_state.get('follow_up_count')}，商机:{behavior_state.get('deal_count')}，风险快照:{behavior_state.get('risk_snapshot_count')}",
                    f"风险轨迹:{behavior_state.get('risk_level_history')}",
                    f"任务结果:{behavior_state.get('task_result_history')}",
                ]
            ),
        ),
        _context_section(
            section_type="compiled_memory",
            title="已编译记忆",
            priority=50,
            source_refs=["customer_memory"],
            content=_join_non_empty(
                [
                    f"memory_id:{memory_state.get('memory_id')}",
                    f"last_compiled_at:{memory_state.get('last_compiled_at')}",
                    memory_state.get("summary_text") or "",
                ]
            ),
        ),
        _context_section(
            section_type="recommended_usage",
            title="使用建议",
            priority=60,
            source_refs=["memory_runtime"],
            content=_join_non_empty(long_term.get("recommended_usage") or []),
        ),
    ]
    packed_sections, compressed_context, overflow = _pack_context_sections(sections, max_chars=char_budget)

    return {
        "source_type": "runtime_context_packet",
        "packet_id": f"context_packet:{customer_id}",
        "customer_id": customer_id,
        "generated_at": datetime.now().isoformat(),
        "budget": {
            "max_chars": char_budget,
            "used_chars": len(compressed_context),
            "overflow": overflow,
        },
        "sections": packed_sections,
        "compressed_context": compressed_context,
        "raw_refs": {
            "working_memory_id": working["memory_id"],
            "long_term_memory_id": long_term["memory_id"],
            "customer_memory_id": memory_state.get("memory_id"),
            "knowledge_citation_count": 0,
        },
    }
