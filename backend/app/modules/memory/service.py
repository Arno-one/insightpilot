from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.agent import chat_session_service, conversation_memory_service
from app.modules.nl2sql import dao as nl2sql_dao


ShortTermSource = Literal["agent_chat", "risk_chat", "nl2sql"]
SOURCE_TYPES: tuple[ShortTermSource, ...] = ("agent_chat", "risk_chat", "nl2sql")


def _loads_metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
