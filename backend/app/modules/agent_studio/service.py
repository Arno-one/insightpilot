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
    if status == "active":
        _disable_active_agent_definitions(db, current_user, agent_code=agent_code)
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


def _disable_active_agent_definitions(
    db: Session,
    current_user: dict[str, Any],
    *,
    agent_code: str,
    exclude_definition_id: str | None = None,
) -> None:
    filters = [
        "tenant_id = :tenant_id",
        "agent_code = :agent_code",
        "status = 'active'",
    ]
    params: dict[str, Any] = {
        "tenant_id": current_user["tenant_id"],
        "agent_code": agent_code,
        "updated_by_user_id": current_user["user_id"],
    }
    if exclude_definition_id:
        filters.append("definition_id <> :exclude_definition_id")
        params["exclude_definition_id"] = exclude_definition_id
    db.execute(
        text(
            f"""
            UPDATE agent_definition
            SET status = 'disabled',
                updated_by_user_id = :updated_by_user_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE {' AND '.join(filters)}
            """
        ),
        params,
    )


def _get_max_agent_version(db: Session, current_user: dict[str, Any], *, agent_code: str) -> int:
    value = db.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) AS max_version
            FROM agent_definition
            WHERE tenant_id = :tenant_id AND agent_code = :agent_code
            """
        ),
        {"tenant_id": current_user["tenant_id"], "agent_code": agent_code},
    ).scalar()
    return int(value or 0)


def clone_agent_definition(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str,
    version: int | None = None,
    status: str = "draft",
    agent_name: str | None = None,
    description: str | None = None,
    config_json: dict[str, Any] | None = None,
    tool_policy_json: dict[str, Any] | None = None,
    memory_policy_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = get_agent_definition(db, current_user, definition_id=definition_id)
    target_version = version if version is not None else _get_max_agent_version(
        db, current_user, agent_code=source["agent_code"]
    ) + 1
    # 中文注释：复制版本时默认继承原配置，只覆盖调用方明确传入的新字段，避免漏传导致配置丢失。
    return create_agent_definition(
        db,
        current_user,
        agent_code=source["agent_code"],
        agent_name=agent_name or source["agent_name"],
        description=source["description"] if description is None else description,
        agent_type=source["agent_type"],
        runtime_type=source["runtime_type"],
        status=status,
        version=target_version,
        config_json=source["config_json"] if config_json is None else config_json,
        tool_policy_json=source["tool_policy_json"] if tool_policy_json is None else tool_policy_json,
        memory_policy_json=source["memory_policy_json"] if memory_policy_json is None else memory_policy_json,
    )


def update_agent_definition_status(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str,
    status: str,
) -> dict[str, Any]:
    item = get_agent_definition(db, current_user, definition_id=definition_id)
    if status == "active":
        # 中文注释：运行时按 agent_code 取版本，保持单 active 可以避免多版本抢占执行入口。
        _disable_active_agent_definitions(
            db,
            current_user,
            agent_code=item["agent_code"],
            exclude_definition_id=definition_id,
        )
    db.execute(
        text(
            """
            UPDATE agent_definition
            SET status = :status,
                updated_by_user_id = :updated_by_user_id,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = :tenant_id AND definition_id = :definition_id
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "definition_id": definition_id,
            "status": status,
            "updated_by_user_id": current_user["user_id"],
        },
    )
    db.commit()
    return get_agent_definition(db, current_user, definition_id=definition_id)


def get_latest_active_agent_definition(
    db: Session,
    current_user: dict[str, Any],
    *,
    agent_code: str,
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT definition_id, agent_code, agent_name, description, agent_type, runtime_type,
                   status, version, config_json, tool_policy_json, memory_policy_json,
                   created_by_user_id, updated_by_user_id, created_at, updated_at
            FROM agent_definition
            WHERE tenant_id = :tenant_id AND agent_code = :agent_code AND status = 'active'
            ORDER BY version DESC, updated_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"tenant_id": current_user["tenant_id"], "agent_code": agent_code},
    ).mappings().first()
    if not row:
        raise ValueError("Agent Definition 最新可用版本不存在")
    return _row_to_agent_definition(row)


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
