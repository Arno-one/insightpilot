import json
from datetime import datetime
from typing import Any

from app.core.redis import get_redis

MAX_RECENT_ROUNDS = 5
MAX_RECENT_MESSAGES = MAX_RECENT_ROUNDS * 2
SUMMARY_CHAR_LIMIT = 2000
MESSAGE_PREVIEW_LIMIT = 120


def build_session_key(tenant_id: str, user_id: str, customer_id: str) -> str:
    """统一 Risk Agent 对话会话键，保证租户、用户、客户三层隔离。"""
    return f"risk_chat:{tenant_id}:{user_id}:{customer_id}"


def _default_memory(session_key: str) -> dict[str, Any]:
    return {
        "session_key": session_key,
        "recent_messages": [],
        "history_summary": "",
        "updated_at": None,
        "memory_window": {
            "recent_rounds": MAX_RECENT_ROUNDS,
            "max_recent_messages": MAX_RECENT_MESSAGES,
        },
    }


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _dumps_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_message_content(content: Any) -> str:
    return " ".join(str(content or "").split()).strip()


def _clip_text(text: str, limit: int = MESSAGE_PREVIEW_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _message_label(role: str) -> str:
    return "用户" if role == "user" else "Risk Agent"


def _serialize_message(role: str, content: str, created_at: str | None = None) -> dict[str, str]:
    return {
        "role": role,
        "content": _normalize_message_content(content),
        "created_at": created_at or datetime.now().isoformat(),
    }


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    """先用确定性摘要压缩更早消息，保证没有 LLM 也能稳定保留上下文。"""
    lines: list[str] = []
    for item in messages:
        role = _message_label(str(item.get("role") or "assistant"))
        content = _clip_text(_normalize_message_content(item.get("content")))
        if content:
            lines.append(f"{role}：{content}")
    return "\n".join(lines).strip()


def _merge_history_summary(existing_summary: str, new_summary: str) -> str:
    parts = [part.strip() for part in [existing_summary, new_summary] if part and part.strip()]
    merged = "\n".join(parts).strip()
    if len(merged) <= SUMMARY_CHAR_LIMIT:
        return merged
    return merged[-SUMMARY_CHAR_LIMIT:]


def load_conversation_memory(
    tenant_id: str,
    user_id: str,
    customer_id: str,
    *,
    redis_client=None,
) -> dict[str, Any]:
    session_key = build_session_key(tenant_id, user_id, customer_id)
    client = redis_client or get_redis()
    stored = _loads_json(client.get(session_key))
    memory = _default_memory(session_key)
    memory.update(
        {
            "recent_messages": list(stored.get("recent_messages") or []),
            "history_summary": str(stored.get("history_summary") or ""),
            "updated_at": stored.get("updated_at"),
        }
    )
    return memory


def save_conversation_memory(
    tenant_id: str,
    user_id: str,
    customer_id: str,
    memory: dict[str, Any],
    *,
    redis_client=None,
) -> dict[str, Any]:
    session_key = build_session_key(tenant_id, user_id, customer_id)
    payload = _default_memory(session_key)
    payload.update(
        {
            "recent_messages": list(memory.get("recent_messages") or []),
            "history_summary": str(memory.get("history_summary") or ""),
            "updated_at": memory.get("updated_at") or datetime.now().isoformat(),
        }
    )
    client = redis_client or get_redis()
    client.set(session_key, _dumps_json(payload))
    return payload


def compact_conversation_memory(memory: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    recent_messages = list(memory.get("recent_messages") or [])
    if len(recent_messages) <= MAX_RECENT_MESSAGES:
        memory["updated_at"] = memory.get("updated_at") or datetime.now().isoformat()
        memory["memory_window"] = {
            "recent_rounds": MAX_RECENT_ROUNDS,
            "max_recent_messages": MAX_RECENT_MESSAGES,
        }
        return memory, False

    overflow_count = len(recent_messages) - MAX_RECENT_MESSAGES
    overflow_messages = recent_messages[:overflow_count]
    retained_messages = recent_messages[overflow_count:]
    memory["recent_messages"] = retained_messages
    memory["history_summary"] = _merge_history_summary(
        str(memory.get("history_summary") or ""),
        _summarize_messages(overflow_messages),
    )
    memory["updated_at"] = datetime.now().isoformat()
    memory["memory_window"] = {
        "recent_rounds": MAX_RECENT_ROUNDS,
        "max_recent_messages": MAX_RECENT_MESSAGES,
    }
    return memory, True


def append_conversation_messages(
    tenant_id: str,
    user_id: str,
    customer_id: str,
    *,
    messages: list[dict[str, str]],
    redis_client=None,
) -> tuple[dict[str, Any], bool]:
    memory = load_conversation_memory(tenant_id, user_id, customer_id, redis_client=redis_client)
    memory["recent_messages"].extend(
        [
            _serialize_message(
                str(item.get("role") or "assistant"),
                str(item.get("content") or ""),
                item.get("created_at"),
            )
            for item in messages
            if _normalize_message_content(item.get("content"))
        ]
    )
    memory["updated_at"] = datetime.now().isoformat()
    memory, compacted = compact_conversation_memory(memory)
    saved = save_conversation_memory(tenant_id, user_id, customer_id, memory, redis_client=redis_client)
    return saved, compacted


def clear_conversation_memory(
    tenant_id: str,
    user_id: str,
    customer_id: str,
    *,
    redis_client=None,
) -> None:
    client = redis_client or get_redis()
    client.delete(build_session_key(tenant_id, user_id, customer_id))
