import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_to_agent_definition(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["config_json"] = _loads(item.get("config_json"))
    item["tool_policy_json"] = _loads(item.get("tool_policy_json"))
    item["memory_policy_json"] = _loads(item.get("memory_policy_json"))
    for key in ["created_at", "updated_at"]:
        value = item.get(key)
        item[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return item


def create_agent_definition(
    db: Session,
    current_user: dict[str, Any],
    *,
    agent_code: str,
    agent_name: str,
    description: str | None,
    agent_type: str,
    runtime_type: str,
    status: str,
    version: int,
    config_json: dict[str, Any] | None = None,
    tool_policy_json: dict[str, Any] | None = None,
    memory_policy_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition_id = new_id("agentdef")
    db.execute(
        text(
            """
            INSERT INTO agent_definition (
              tenant_id, definition_id, agent_code, agent_name, description, agent_type,
              runtime_type, status, version, config_json, tool_policy_json, memory_policy_json,
              created_by_user_id, updated_by_user_id
            )
            VALUES (
              :tenant_id, :definition_id, :agent_code, :agent_name, :description, :agent_type,
              :runtime_type, :status, :version, :config_json, :tool_policy_json, :memory_policy_json,
              :created_by_user_id, :updated_by_user_id
            )
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "definition_id": definition_id,
            "agent_code": agent_code,
            "agent_name": agent_name,
            "description": description,
            "agent_type": agent_type,
            "runtime_type": runtime_type,
            "status": status,
            "version": version,
            "config_json": _dumps(config_json),
            "tool_policy_json": _dumps(tool_policy_json),
            "memory_policy_json": _dumps(memory_policy_json),
            "created_by_user_id": current_user["user_id"],
            "updated_by_user_id": current_user["user_id"],
        },
    )
    db.commit()
    return get_agent_definition(db, current_user, definition_id=definition_id)


def list_agent_definitions(
    db: Session,
    current_user: dict[str, Any],
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": current_user["tenant_id"], "limit": max(1, min(limit, 100))}
    if status:
        filters.append("status = :status")
        params["status"] = status
    rows = db.execute(
        text(
            f"""
            SELECT definition_id, agent_code, agent_name, description, agent_type, runtime_type,
                   status, version, config_json, tool_policy_json, memory_policy_json,
                   created_by_user_id, updated_by_user_id, created_at, updated_at
            FROM agent_definition
            WHERE {' AND '.join(filters)}
            ORDER BY updated_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_row_to_agent_definition(row) for row in rows]


def get_agent_definition(db: Session, current_user: dict[str, Any], *, definition_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT definition_id, agent_code, agent_name, description, agent_type, runtime_type,
                   status, version, config_json, tool_policy_json, memory_policy_json,
                   created_by_user_id, updated_by_user_id, created_at, updated_at
            FROM agent_definition
            WHERE tenant_id = :tenant_id AND definition_id = :definition_id
            LIMIT 1
            """
        ),
        {"tenant_id": current_user["tenant_id"], "definition_id": definition_id},
    ).mappings().first()
    if not row:
        raise ValueError("Agent Definition 不存在")
    return _row_to_agent_definition(row)
