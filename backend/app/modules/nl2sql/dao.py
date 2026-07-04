import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def dumps_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        data = json.loads(value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def row_to_session(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["context_json"] = loads_json(item.get("context_json"))
    return item


def row_to_message(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["metadata_json"] = loads_json(item.get("metadata_json"))
    item["result_json"] = loads_json(item.get("result_json"))
    item["is_cached"] = bool(item.get("is_cached"))
    return item


def row_to_audit(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["validator_result_json"] = loads_json(item.get("validator_result_json"))
    item["execution_summary_json"] = loads_json(item.get("execution_summary_json"))
    return item


def create_session(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    title: str,
    data_scope: str,
    context_json: dict[str, Any] | None,
) -> dict[str, Any]:
    session_id = new_id("nl2sql_sess")
    db.execute(
        text(
            """
            INSERT INTO nl2sql_session (
              tenant_id, session_id, user_id, title, data_scope, context_json
            )
            VALUES (
              :tenant_id, :session_id, :user_id, :title, :data_scope, :context_json
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "session_id": session_id,
            "user_id": user_id,
            "title": title,
            "data_scope": data_scope,
            "context_json": dumps_json(context_json),
        },
    )
    db.commit()
    return get_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)


def get_session(db: Session, *, tenant_id: str, user_id: str, session_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT session_id, tenant_id, user_id, title, status, data_scope, context_json,
                   last_question, last_query_status, message_count, last_message_at, created_at, updated_at
            FROM nl2sql_session
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND session_id = :session_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id},
    ).mappings().first()
    if not row:
        raise ValueError("NL2SQL 会话不存在或无权访问")
    return row_to_session(row)


def list_sessions(db: Session, *, tenant_id: str, user_id: str, status: str = "active", limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT session_id, tenant_id, user_id, title, status, data_scope, context_json,
                   last_question, last_query_status, message_count, last_message_at, created_at, updated_at
            FROM nl2sql_session
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND status = :status
            ORDER BY COALESCE(last_message_at, updated_at, created_at) DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "status": status, "limit": max(1, min(limit, 100))},
    ).mappings().all()
    return [row_to_session(row) for row in rows]


def append_message(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    query_id: str | None = None,
    question: str | None = None,
    generated_sql: str | None = None,
    result_json: dict[str, Any] | None = None,
    cost_ms: int = 0,
    is_cached: bool = False,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    get_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    message_id = new_id("nl2sql_msg")
    created_at = datetime.now()
    db.execute(
        text(
            """
            INSERT INTO nl2sql_message (
              tenant_id, message_id, session_id, user_id, role, content, query_id, question,
              generated_sql, result_json, cost_ms, is_cached, metadata_json, created_at
            )
            VALUES (
              :tenant_id, :message_id, :session_id, :user_id, :role, :content, :query_id, :question,
              :generated_sql, :result_json, :cost_ms, :is_cached, :metadata_json, :created_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "message_id": message_id,
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": " ".join(content.split()).strip(),
            "query_id": query_id,
            "question": question,
            "generated_sql": generated_sql,
            "result_json": dumps_json(result_json),
            "cost_ms": cost_ms,
            "is_cached": 1 if is_cached else 0,
            "metadata_json": dumps_json(metadata_json),
            "created_at": created_at,
        },
    )
    db.execute(
        text(
            """
            UPDATE nl2sql_session
            SET message_count = message_count + 1,
                last_message_at = :last_message_at
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND session_id = :session_id
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id, "last_message_at": created_at},
    )
    db.commit()
    return get_message(db, tenant_id=tenant_id, user_id=user_id, message_id=message_id)


def get_message(db: Session, *, tenant_id: str, user_id: str, message_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT message_id, tenant_id, session_id, user_id, role, content, query_id, question,
                   generated_sql, result_json, cost_ms, is_cached, metadata_json, created_at
            FROM nl2sql_message
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND message_id = :message_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "message_id": message_id},
    ).mappings().first()
    if not row:
        raise ValueError("NL2SQL 消息不存在或无权访问")
    return row_to_message(row)


def list_messages(db: Session, *, tenant_id: str, user_id: str, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    get_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    rows = db.execute(
        text(
            """
            SELECT message_id, tenant_id, session_id, user_id, role, content, query_id, question,
                   generated_sql, result_json, cost_ms, is_cached, metadata_json, created_at
            FROM nl2sql_message
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND session_id = :session_id
            ORDER BY created_at ASC, id ASC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id, "limit": max(1, min(limit, 500))},
    ).mappings().all()
    return [row_to_message(row) for row in rows]


def create_query_audit(db: Session, *, tenant_id: str, user_id: str, session_id: str, question: str) -> dict[str, Any]:
    get_session(db, tenant_id=tenant_id, user_id=user_id, session_id=session_id)
    query_id = new_id("nl2sql_query")
    db.execute(
        text(
            """
            INSERT INTO nl2sql_query_audit (
              tenant_id, query_id, session_id, user_id, question, status
            )
            VALUES (
              :tenant_id, :query_id, :session_id, :user_id, :question, 'created'
            )
            """
        ),
        {"tenant_id": tenant_id, "query_id": query_id, "session_id": session_id, "user_id": user_id, "question": question},
    )
    db.execute(
        text(
            """
            UPDATE nl2sql_session
            SET last_question = :question,
                last_query_status = 'created'
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND session_id = :session_id
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": session_id, "question": question},
    )
    db.commit()
    return get_query_audit(db, tenant_id=tenant_id, user_id=user_id, query_id=query_id)


def update_query_audit(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    query_id: str,
    generated_sql: str | None = None,
    normalized_sql: str | None = None,
    status: str,
    validator_result_json: dict[str, Any] | None = None,
    execution_summary_json: dict[str, Any] | None = None,
    row_count: int | None = None,
    error_message: str | None = None,
    elapsed_ms: int = 0,
) -> dict[str, Any]:
    current = get_query_audit(db, tenant_id=tenant_id, user_id=user_id, query_id=query_id)
    db.execute(
        text(
            """
            UPDATE nl2sql_query_audit
            SET generated_sql = :generated_sql,
                normalized_sql = :normalized_sql,
                status = :status,
                validator_result_json = :validator_result_json,
                execution_summary_json = :execution_summary_json,
                row_count = :row_count,
                error_message = :error_message,
                elapsed_ms = :elapsed_ms,
                finished_at = CURRENT_TIMESTAMP
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND query_id = :query_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "query_id": query_id,
            "generated_sql": generated_sql,
            "normalized_sql": normalized_sql,
            "status": status,
            "validator_result_json": dumps_json(validator_result_json),
            "execution_summary_json": dumps_json(execution_summary_json),
            "row_count": row_count,
            "error_message": error_message,
            "elapsed_ms": elapsed_ms,
        },
    )
    db.execute(
        text(
            """
            UPDATE nl2sql_session
            SET last_query_status = :status
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND session_id = :session_id
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "session_id": current["session_id"], "status": status},
    )
    db.commit()
    return get_query_audit(db, tenant_id=tenant_id, user_id=user_id, query_id=query_id)


def get_query_audit(db: Session, *, tenant_id: str, user_id: str, query_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT query_id, tenant_id, session_id, user_id, question, generated_sql, normalized_sql,
                   status, validator_result_json, execution_summary_json, row_count, error_message,
                   elapsed_ms, created_at, finished_at
            FROM nl2sql_query_audit
            WHERE tenant_id = :tenant_id AND user_id = :user_id AND query_id = :query_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id, "query_id": query_id},
    ).mappings().first()
    if not row:
        raise ValueError("NL2SQL 查询审计不存在或无权访问")
    return row_to_audit(row)
