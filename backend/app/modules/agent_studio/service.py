import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.agent.platform import list_agent_chat_tool_specs
from app.shared.ids import new_id
from app.shared.tenant_boundary import require_current_tenant, tenant_params


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
    item.pop("_tenant_id", None)
    item["config_json"] = _loads(item.get("config_json"))
    item["tool_policy_json"] = _loads(item.get("tool_policy_json"))
    item["memory_policy_json"] = _loads(item.get("memory_policy_json"))
    for key in ["created_at", "updated_at"]:
        value = item.get(key)
        item[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return item


def _row_to_publish_audit(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["validation_json"] = _loads(item.get("validation_json"))
    for key in ["created_at"]:
        value = item.get(key)
        item[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return item


def _to_iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


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


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_tool_manifest(tool_policy: dict[str, Any], current_user: dict[str, Any]) -> dict[str, Any]:
    tool_specs = list_agent_chat_tool_specs(current_user)
    specs_by_name = {item["name"]: item for item in tool_specs}
    allowed_tools = _normalize_string_list(tool_policy.get("allowed_tools"))
    denied_tools = set(_normalize_string_list(tool_policy.get("denied_tools")))
    selected_names = allowed_tools or []
    enabled_tools = [
        specs_by_name[name]
        for name in selected_names
        if name in specs_by_name and specs_by_name[name].get("available") and name not in denied_tools
    ]
    blocked_tools = [
        specs_by_name[name]
        for name in selected_names
        if name in specs_by_name and (not specs_by_name[name].get("available") or name in denied_tools)
    ]
    missing_tools = [name for name in selected_names if name not in specs_by_name]
    # 中文注释：Manifest 只暴露定义显式允许的工具，避免 Agent 发布后意外继承新增工具能力。
    return {
        "router": tool_policy.get("router") or "agent_chat_tool_router_v1",
        "allowed_tools": allowed_tools,
        "denied_tools": sorted(denied_tools),
        "enabled_tools": enabled_tools,
        "blocked_tools": blocked_tools,
        "missing_tools": missing_tools,
        "registry_tool_count": len(tool_specs),
    }


def build_agent_manifest(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str | None = None,
    agent_code: str | None = None,
) -> dict[str, Any]:
    if definition_id:
        definition = get_agent_definition(db, current_user, definition_id=definition_id)
    elif agent_code:
        definition = get_latest_active_agent_definition(db, current_user, agent_code=agent_code)
    else:
        raise ValueError("必须提供 definition_id 或 agent_code")

    config = definition["config_json"]
    tool_policy = definition["tool_policy_json"]
    memory_policy = definition["memory_policy_json"]
    return {
        "manifest_version": "agent_manifest_v1",
        "tenant_id": current_user["tenant_id"],
        "definition": {
            "definition_id": definition["definition_id"],
            "agent_code": definition["agent_code"],
            "agent_name": definition["agent_name"],
            "description": definition["description"],
            "agent_type": definition["agent_type"],
            "runtime_type": definition["runtime_type"],
            "status": definition["status"],
            "version": definition["version"],
        },
        "runtime": {
            "runtime_type": definition["runtime_type"],
            "entrypoint": config.get("entrypoint"),
            "config": config,
        },
        "tool_manifest": _build_tool_manifest(tool_policy, current_user),
        "memory_manifest": {
            "enabled": bool(memory_policy),
            "context_packet": bool(memory_policy.get("context_packet")),
            "max_chars": _safe_int(memory_policy.get("max_chars")),
            "policy": memory_policy,
        },
        "governance": {
            "requires_active_for_code_lookup": True,
            "single_active_version": True,
            "loaded_by_user_id": current_user["user_id"],
        },
    }


def validate_agent_tool_policy(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str | None = None,
    agent_code: str | None = None,
) -> dict[str, Any]:
    manifest = build_agent_manifest(db, current_user, definition_id=definition_id, agent_code=agent_code)
    tool_manifest = manifest["tool_manifest"]
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for tool_name in tool_manifest["missing_tools"]:
        errors.append(
            {
                "code": "tool_not_registered",
                "tool_name": tool_name,
                "message": "工具未注册，Agent 运行时无法调用",
            }
        )

    denied_tools = set(tool_manifest["denied_tools"])
    for tool in tool_manifest["blocked_tools"]:
        tool_name = tool["name"]
        if tool_name in denied_tools:
            errors.append(
                {
                    "code": "tool_denied_by_policy",
                    "tool_name": tool_name,
                    "message": "工具同时出现在允许和禁用策略中",
                }
            )
            continue
        errors.append(
            {
                "code": "tool_permission_missing",
                "tool_name": tool_name,
                "required_permissions": tool.get("required_permissions", []),
                "message": "当前用户缺少工具所需权限",
            }
        )

    if not tool_manifest["allowed_tools"]:
        warnings.append(
            {
                "code": "empty_allowed_tools",
                "message": "当前 Agent 未声明可用工具，运行时只能执行纯对话或后续兼容路径",
            }
        )

    # 中文注释：校验结果保持只读，先为发布页和自动化门禁提供依据，不在本轮改变发布行为。
    return {
        "validation_version": "agent_tool_policy_validation_v1",
        "valid": not errors,
        "definition": manifest["definition"],
        "summary": {
            "allowed_count": len(tool_manifest["allowed_tools"]),
            "enabled_count": len(tool_manifest["enabled_tools"]),
            "blocked_count": len(tool_manifest["blocked_tools"]),
            "missing_count": len(tool_manifest["missing_tools"]),
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "errors": errors,
        "warnings": warnings,
        "tool_manifest": tool_manifest,
    }


def validate_agent_runtime_config(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str | None = None,
    agent_code: str | None = None,
) -> dict[str, Any]:
    manifest = build_agent_manifest(db, current_user, definition_id=definition_id, agent_code=agent_code)
    runtime = manifest["runtime"]
    runtime_type = runtime.get("runtime_type")
    entrypoint = runtime.get("entrypoint")
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if runtime_type not in {"chat", "workflow", "tool_agent"}:
        errors.append(
            {
                "code": "runtime_type_invalid",
                "runtime_type": runtime_type,
                "message": "Runtime 类型不在平台支持范围内",
            }
        )

    if runtime_type in {"workflow", "tool_agent"} and not str(entrypoint or "").strip():
        errors.append(
            {
                "code": "runtime_entrypoint_missing",
                "runtime_type": runtime_type,
                "message": "workflow/tool_agent 类型必须配置 entrypoint",
            }
        )

    if entrypoint is not None and not isinstance(entrypoint, str):
        errors.append(
            {
                "code": "runtime_entrypoint_invalid",
                "message": "entrypoint 必须是字符串",
            }
        )

    if runtime_type == "chat" and not str(entrypoint or "").strip():
        warnings.append(
            {
                "code": "chat_entrypoint_empty",
                "message": "chat 类型未配置 entrypoint，将由默认对话 Runtime 承接",
            }
        )

    # 中文注释：Runtime Config 校验先覆盖能否执行的关键入口，后续再扩展参数 schema 校验。
    return {
        "validation_version": "agent_runtime_config_validation_v1",
        "valid": not errors,
        "definition": manifest["definition"],
        "summary": {
            "runtime_type": runtime_type,
            "has_entrypoint": bool(str(entrypoint or "").strip()),
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "errors": errors,
        "warnings": warnings,
        "runtime": runtime,
    }


def validate_agent_memory_policy(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str | None = None,
    agent_code: str | None = None,
) -> dict[str, Any]:
    manifest = build_agent_manifest(db, current_user, definition_id=definition_id, agent_code=agent_code)
    memory_manifest = manifest["memory_manifest"]
    policy = memory_manifest["policy"]
    context_packet = policy.get("context_packet")
    max_chars_value = policy.get("max_chars")
    max_chars = _safe_int(max_chars_value)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not policy:
        warnings.append(
            {
                "code": "memory_policy_empty",
                "message": "当前 Agent 未配置记忆策略，将按默认无上下文包策略运行",
            }
        )

    if context_packet is not None and not isinstance(context_packet, bool):
        errors.append(
            {
                "code": "memory_context_packet_invalid",
                "message": "context_packet 必须是布尔值",
            }
        )

    if context_packet is True and max_chars <= 0:
        errors.append(
            {
                "code": "memory_max_chars_missing",
                "message": "启用 context_packet 时必须配置 max_chars",
            }
        )
    elif max_chars_value is not None and not isinstance(max_chars_value, int):
        errors.append(
            {
                "code": "memory_max_chars_invalid",
                "message": "max_chars 必须是整数",
            }
        )
    elif max_chars and (max_chars < 500 or max_chars > 12000):
        errors.append(
            {
                "code": "memory_max_chars_out_of_range",
                "max_chars": max_chars,
                "message": "max_chars 必须在 500 到 12000 之间",
            }
        )

    # 中文注释：Memory Policy 校验防止上下文包过大或配置类型错误，避免运行时上下文失控。
    return {
        "validation_version": "agent_memory_policy_validation_v1",
        "valid": not errors,
        "definition": manifest["definition"],
        "summary": {
            "enabled": memory_manifest["enabled"],
            "context_packet": memory_manifest["context_packet"],
            "max_chars": memory_manifest["max_chars"],
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "errors": errors,
        "warnings": warnings,
        "memory_manifest": memory_manifest,
    }


def validate_agent_publish_readiness(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str,
) -> dict[str, Any]:
    tool_validation = validate_agent_tool_policy(db, current_user, definition_id=definition_id)
    runtime_validation = validate_agent_runtime_config(db, current_user, definition_id=definition_id)
    memory_validation = validate_agent_memory_policy(db, current_user, definition_id=definition_id)
    errors = [*tool_validation["errors"], *runtime_validation["errors"], *memory_validation["errors"]]
    warnings = [*tool_validation["warnings"], *runtime_validation["warnings"], *memory_validation["warnings"]]
    return {
        "validation_version": "agent_publish_readiness_v1",
        "valid": not errors,
        "definition": tool_validation["definition"],
        "summary": {
            "tool_error_count": tool_validation["summary"]["error_count"],
            "runtime_error_count": runtime_validation["summary"]["error_count"],
            "memory_error_count": memory_validation["summary"]["error_count"],
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "tool_policy": tool_validation,
            "runtime_config": runtime_validation,
            "memory_policy": memory_validation,
        },
    }


def publish_agent_definition(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str,
) -> dict[str, Any]:
    validation = validate_agent_publish_readiness(db, current_user, definition_id=definition_id)
    if not validation["valid"]:
        audit = create_agent_publish_audit(
            db,
            current_user,
            definition=validation["definition"],
            published=False,
            validation=validation,
            message="Agent Definition 未通过发布门禁",
        )
        return {
            "published": False,
            "definition": validation["definition"],
            "validation": validation,
            "publish_audit": audit,
            "message": "Agent Definition 未通过发布门禁",
        }

    published = update_agent_definition_status(db, current_user, definition_id=definition_id, status="active")
    audit = create_agent_publish_audit(
        db,
        current_user,
        definition=published,
        published=True,
        validation=validation,
        message="Agent Definition 已发布",
    )
    return {
        "published": True,
        "definition": published,
        "validation": validation,
        "publish_audit": audit,
        "message": "Agent Definition 已发布",
    }


def rollback_agent_definition(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str,
) -> dict[str, Any]:
    validation = validate_agent_publish_readiness(db, current_user, definition_id=definition_id)
    if not validation["valid"]:
        audit = create_agent_publish_audit(
            db,
            current_user,
            definition=validation["definition"],
            published=False,
            validation=validation,
            message="Agent Definition 回滚被门禁阻断",
        )
        return {
            "rolled_back": False,
            "definition": validation["definition"],
            "validation": validation,
            "publish_audit": audit,
            "message": "Agent Definition 回滚被门禁阻断",
        }

    # 中文注释：回滚本质是把历史版本重新发布为 active，仍复用单 active 版本约束。
    rolled_back = update_agent_definition_status(db, current_user, definition_id=definition_id, status="active")
    audit = create_agent_publish_audit(
        db,
        current_user,
        definition=rolled_back,
        published=True,
        validation=validation,
        message="Agent Definition 已回滚发布",
    )
    return {
        "rolled_back": True,
        "definition": rolled_back,
        "validation": validation,
        "publish_audit": audit,
        "message": "Agent Definition 已回滚发布",
    }


def _append_diff(changes: list[dict[str, Any]], path: str, before: Any, after: Any) -> None:
    if before == after:
        return
    changes.append(
        {
            "path": path,
            "before": before,
            "after": after,
        }
    )


def _diff_dict(before: dict[str, Any], after: dict[str, Any], *, prefix: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before.keys()) | set(after.keys())):
        before_value = before.get(key)
        after_value = after.get(key)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(before_value, dict) and isinstance(after_value, dict):
            changes.extend(_diff_dict(before_value, after_value, prefix=path))
            continue
        _append_diff(changes, path, before_value, after_value)
    return changes


def diff_agent_definitions(
    db: Session,
    current_user: dict[str, Any],
    *,
    base_definition_id: str,
    target_definition_id: str,
) -> dict[str, Any]:
    base = get_agent_definition(db, current_user, definition_id=base_definition_id)
    target = get_agent_definition(db, current_user, definition_id=target_definition_id)
    metadata_fields = ["agent_code", "agent_name", "description", "agent_type", "runtime_type", "status", "version"]
    metadata_changes: list[dict[str, Any]] = []
    for field in metadata_fields:
        _append_diff(metadata_changes, f"definition.{field}", base.get(field), target.get(field))

    config_changes = _diff_dict(base["config_json"], target["config_json"], prefix="config_json")
    tool_policy_changes = _diff_dict(base["tool_policy_json"], target["tool_policy_json"], prefix="tool_policy_json")
    memory_policy_changes = _diff_dict(
        base["memory_policy_json"],
        target["memory_policy_json"],
        prefix="memory_policy_json",
    )
    changes = [*metadata_changes, *config_changes, *tool_policy_changes, *memory_policy_changes]
    # 中文注释：Diff 只做结构化只读对比，不修改定义，供发布评审和回滚前确认使用。
    return {
        "diff_version": "agent_definition_diff_v1",
        "base_definition": {
            "definition_id": base["definition_id"],
            "agent_code": base["agent_code"],
            "version": base["version"],
            "status": base["status"],
        },
        "target_definition": {
            "definition_id": target["definition_id"],
            "agent_code": target["agent_code"],
            "version": target["version"],
            "status": target["status"],
        },
        "summary": {
            "changed": bool(changes),
            "changed_count": len(changes),
            "metadata_change_count": len(metadata_changes),
            "config_change_count": len(config_changes),
            "tool_policy_change_count": len(tool_policy_changes),
            "memory_policy_change_count": len(memory_policy_changes),
        },
        "changed_paths": [item["path"] for item in changes],
        "changes": {
            "metadata": metadata_changes,
            "config_json": config_changes,
            "tool_policy_json": tool_policy_changes,
            "memory_policy_json": memory_policy_changes,
        },
    }


def summarize_agent_studio(db: Session, current_user: dict[str, Any]) -> dict[str, Any]:
    definition_row = db.execute(
        text(
            """
            SELECT COUNT(*) AS total_count,
                   COUNT(DISTINCT agent_code) AS agent_code_count,
                   SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) AS draft_count,
                   SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_count,
                   SUM(CASE WHEN status = 'disabled' THEN 1 ELSE 0 END) AS disabled_count,
                   MAX(updated_at) AS latest_definition_updated_at
            FROM agent_definition
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().first() or {}
    audit_row = db.execute(
        text(
            """
            SELECT COUNT(*) AS total_count,
                   SUM(CASE WHEN publish_status = 'published' THEN 1 ELSE 0 END) AS published_count,
                   SUM(CASE WHEN publish_status = 'blocked' THEN 1 ELSE 0 END) AS blocked_count,
                   MAX(created_at) AS latest_publish_audit_at
            FROM agent_definition_publish_audit
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().first() or {}
    active_definitions = list_agent_definitions(db, current_user, status="active", limit=10)
    recent_audits = list_agent_publish_audits(db, current_user, limit=10)
    # 中文注释：阶段总览只聚合平台化指标，不读取具体业务客户数据，避免跨模块耦合。
    return {
        "overview_version": "agent_studio_overview_v1",
        "definition_summary": {
            "total_count": int(definition_row.get("total_count") or 0),
            "agent_code_count": int(definition_row.get("agent_code_count") or 0),
            "draft_count": int(definition_row.get("draft_count") or 0),
            "active_count": int(definition_row.get("active_count") or 0),
            "disabled_count": int(definition_row.get("disabled_count") or 0),
            "latest_definition_updated_at": _to_iso(definition_row.get("latest_definition_updated_at")),
        },
        "publish_audit_summary": {
            "total_count": int(audit_row.get("total_count") or 0),
            "published_count": int(audit_row.get("published_count") or 0),
            "blocked_count": int(audit_row.get("blocked_count") or 0),
            "latest_publish_audit_at": _to_iso(audit_row.get("latest_publish_audit_at")),
        },
        "active_definitions": active_definitions,
        "recent_publish_audits": recent_audits,
    }


def create_agent_publish_audit(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition: dict[str, Any],
    published: bool,
    validation: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    audit_id = new_id("agentaudit")
    summary = validation.get("summary") or {}
    db.execute(
        text(
            """
            INSERT INTO agent_definition_publish_audit (
              tenant_id, audit_id, definition_id, agent_code, version, publish_status,
              validation_json, error_count, warning_count, message, published_by_user_id
            )
            VALUES (
              :tenant_id, :audit_id, :definition_id, :agent_code, :version, :publish_status,
              :validation_json, :error_count, :warning_count, :message, :published_by_user_id
            )
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "audit_id": audit_id,
            "definition_id": definition["definition_id"],
            "agent_code": definition["agent_code"],
            "version": definition["version"],
            "publish_status": "published" if published else "blocked",
            "validation_json": _dumps(validation),
            "error_count": int(summary.get("error_count") or 0),
            "warning_count": int(summary.get("warning_count") or 0),
            "message": message,
            "published_by_user_id": current_user["user_id"],
        },
    )
    db.commit()
    return get_agent_publish_audit(db, current_user, audit_id=audit_id)


def get_agent_publish_audit(db: Session, current_user: dict[str, Any], *, audit_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT audit_id, definition_id, agent_code, version, publish_status,
                   validation_json, error_count, warning_count, message,
                   published_by_user_id, created_at
            FROM agent_definition_publish_audit
            WHERE tenant_id = :tenant_id AND audit_id = :audit_id
            LIMIT 1
            """
        ),
        {"tenant_id": current_user["tenant_id"], "audit_id": audit_id},
    ).mappings().first()
    if not row:
        raise ValueError("Agent 发布审计记录不存在")
    return _row_to_publish_audit(row)


def list_agent_publish_audits(
    db: Session,
    current_user: dict[str, Any],
    *,
    definition_id: str | None = None,
    agent_code: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": current_user["tenant_id"], "limit": max(1, min(limit, 100))}
    if definition_id:
        filters.append("definition_id = :definition_id")
        params["definition_id"] = definition_id
    if agent_code:
        filters.append("agent_code = :agent_code")
        params["agent_code"] = agent_code
    rows = db.execute(
        text(
            f"""
            SELECT audit_id, definition_id, agent_code, version, publish_status,
                   validation_json, error_count, warning_count, message,
                   published_by_user_id, created_at
            FROM agent_definition_publish_audit
            WHERE {' AND '.join(filters)}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_row_to_publish_audit(row) for row in rows]


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
            SELECT tenant_id AS _tenant_id,
                   definition_id, agent_code, agent_name, description, agent_type, runtime_type,
                   status, version, config_json, tool_policy_json, memory_policy_json,
                   created_by_user_id, updated_by_user_id, created_at, updated_at
            FROM agent_definition
            WHERE tenant_id = :tenant_id AND definition_id = :definition_id
            LIMIT 1
            """
        ),
        tenant_params(current_user, definition_id=definition_id),
    ).mappings().first()
    if not row:
        raise ValueError("Agent Definition 不存在")
    require_current_tenant(current_user, row["_tenant_id"], resource_name="Agent Definition")
    return _row_to_agent_definition(row)
