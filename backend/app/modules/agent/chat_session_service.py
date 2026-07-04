import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


MESSAGE_PREVIEW_LIMIT = 120
DEFAULT_SESSION_TITLE = "新对话"


def _now() -> datetime:
    return datetime.now()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _clip_text(value: Any, limit: int = MESSAGE_PREVIEW_LIMIT) -> str:
    text_value = _normalize_text(value)
    if len(text_value) <= limit:
        return text_value
    return f"{text_value[:limit].rstrip()}..."


def _dumps_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _row_to_session(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["context_json"] = _loads_json(item.get("context_json"))
    return item


def _row_to_message(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["metadata_json"] = _loads_json(item.get("metadata_json"))
    return item


def build_memory_key(tenant_id: str, user_id: str, session_id: str) -> str:
    """统一生成短期记忆键；后续 Risk Chat / Data Query 都可以挂到同一套规则。"""
    return f"agent_chat:{tenant_id}:{user_id}:{session_id}"


def create_chat_session(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    agent_scope: str = "general",
    intent: str = "unknown",
    title: str | None = None,
    related_customer_id: str | None = None,
    memory_key: str | None = None,
    context_json: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """创建统一 Agent 会话；V1 只负责会话事实落库，不绑定具体 Runtime 执行。"""
    resolved_session_id = session_id or _new_id("chat_sess")
    resolved_memory_key = memory_key or build_memory_key(tenant_id, user_id, resolved_session_id)
    db.execute(
        text(
            """
            INSERT INTO agent_chat_session (
              tenant_id, session_id, user_id, agent_scope, intent, title, related_customer_id,
              memory_key, context_json
            )
            VALUES (
              :tenant_id, :session_id, :user_id, :agent_scope, :intent, :title, :related_customer_id,
              :memory_key, :context_json
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "session_id": resolved_session_id,
            "user_id": user_id,
            "agent_scope": agent_scope,
            "intent": intent,
            "title": _clip_text(title or DEFAULT_SESSION_TITLE, 120) or DEFAULT_SESSION_TITLE,
            "related_customer_id": related_customer_id,
            "memory_key": resolved_memory_key,
            "context_json": _dumps_json(context_json),
        },
    )
    db.commit()
    return get_chat_session(db, tenant_id=tenant_id, user_id=user_id, session_id=resolved_session_id)


def get_chat_session(db: Session, *, tenant_id: str, user_id: str, session_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT session_id, tenant_id, user_id, agent_scope, intent, title, status,
                   related_customer_id, memory_key, context_json, last_message_role,
                   last_message_preview, message_count, last_message_at, created_at, updated_at
            FROM agent_chat_session
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND session_id = :session_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id},
    ).mappings().first()
    if not row:
        raise ValueError("统一 Agent 对话会话不存在或无权访问")
    return _row_to_session(row)


def list_chat_sessions(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    agent_scope: str | None = None,
    status: str = "active",
    recovery_status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters = ["tenant_id = :tenant_id", "user_id = :user_id", "status = :status"]
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "status": status,
        "limit": max(1, min(limit, 100)),
    }
    if agent_scope:
        filters.append("agent_scope = :agent_scope")
        params["agent_scope"] = agent_scope
    if recovery_status:
        recovery_filter = """
        EXISTS (
          SELECT 1
          FROM agent_chat_message acm
          WHERE acm.tenant_id = agent_chat_session.tenant_id
            AND acm.user_id = agent_chat_session.user_id
            AND acm.session_id = agent_chat_session.session_id
            AND acm.tool_name = 'agent_chat.recovery_event'
        """
        if recovery_status != "any":
            recovery_filter += """
            AND JSON_UNQUOTE(JSON_EXTRACT(acm.metadata_json, '$.recovery_event.status')) = :recovery_status
            """
            params["recovery_status"] = recovery_status
        recovery_filter += ")"
        filters.append(recovery_filter)

    rows = db.execute(
        text(
            f"""
            SELECT session_id, tenant_id, user_id, agent_scope, intent, title, status,
                   related_customer_id, memory_key, context_json, last_message_role,
                   last_message_preview, message_count, last_message_at, created_at, updated_at
            FROM agent_chat_session
            WHERE {' AND '.join(filters)}
            ORDER BY COALESCE(last_message_at, updated_at, created_at) DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_row_to_session(row) for row in rows]


def append_chat_message(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    tool_name: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """追加单条统一消息，并同步刷新会话摘要字段。"""
    normalized_content = _normalize_text(content)
    if not normalized_content:
        raise ValueError("消息内容不能为空")

    session = get_chat_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    resolved_message_id = message_id or _new_id("chat_msg")
    created_at = _now()

    db.execute(
        text(
            """
            INSERT INTO agent_chat_message (
              tenant_id, message_id, session_id, user_id, role, content, intent, tool_name,
              run_id, trace_id, metadata_json, created_at
            )
            VALUES (
              :tenant_id, :message_id, :session_id, :user_id, :role, :content, :intent, :tool_name,
              :run_id, :trace_id, :metadata_json, :created_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "message_id": resolved_message_id,
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": normalized_content,
            "intent": intent,
            "tool_name": tool_name,
            "run_id": run_id,
            "trace_id": trace_id,
            "metadata_json": _dumps_json(metadata_json),
            "created_at": created_at,
        },
    )
    db.execute(
        text(
            """
            UPDATE agent_chat_session
            SET last_message_role = :role,
                last_message_preview = :preview,
                last_message_at = :last_message_at,
                message_count = message_count + 1,
                intent = CASE WHEN intent = 'unknown' AND :intent IS NOT NULL THEN :intent ELSE intent END
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND session_id = :session_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "preview": _clip_text(normalized_content),
            "last_message_at": created_at,
            "intent": intent or session.get("intent"),
        },
    )
    db.commit()
    return get_chat_message(db, tenant_id=tenant_id, user_id=user_id, message_id=resolved_message_id)


def append_chat_messages(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """批量追加消息；V1 保持逐条写入，便于每条消息都有独立审计主键。"""
    return [
        append_chat_message(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            role=str(item.get("role") or "assistant"),
            content=str(item.get("content") or ""),
            intent=item.get("intent"),
            tool_name=item.get("tool_name"),
            run_id=item.get("run_id"),
            trace_id=item.get("trace_id"),
            metadata_json=item.get("metadata_json"),
            message_id=item.get("message_id"),
        )
        for item in messages
    ]


def get_chat_message(db: Session, *, tenant_id: str, user_id: str, message_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT message_id, tenant_id, session_id, user_id, role, content, intent, tool_name,
                   run_id, trace_id, metadata_json, created_at
            FROM agent_chat_message
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND message_id = :message_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "message_id": message_id},
    ).mappings().first()
    if not row:
        raise ValueError("统一 Agent 对话消息不存在或无权访问")
    return _row_to_message(row)


def list_chat_messages(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    get_chat_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    rows = db.execute(
        text(
            """
            SELECT message_id, tenant_id, session_id, user_id, role, content, intent, tool_name,
                   run_id, trace_id, metadata_json, created_at
            FROM agent_chat_message
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND session_id = :session_id
            ORDER BY created_at ASC, id ASC
            LIMIT :limit
            """
        ),
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "limit": max(1, min(limit, 500)),
        },
    ).mappings().all()
    return [_row_to_message(row) for row in rows]


def close_chat_session(db: Session, *, tenant_id: str, user_id: str, session_id: str) -> dict[str, Any]:
    """关闭会话但保留消息审计；清空属于具体业务入口后续再按入口实现。"""
    get_chat_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    db.execute(
        text(
            """
            UPDATE agent_chat_session
            SET status = 'closed'
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND session_id = :session_id
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id},
    )
    db.commit()
    return get_chat_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
