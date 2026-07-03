from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.agent.platform.mcp_gateway import build_shared_mcp_gateway
from app.modules.agent.platform.tool_registry import ToolExecutionContext
from app.shared.ids import new_id

ACTION_RUN_STATUS_RUNNING = "running"
ACTION_RUN_STATUS_SUCCESS = "success"
ACTION_RUN_STATUS_FAILED = "failed"

ACTION_STEP_STATUS_RUNNING = "running"
ACTION_STEP_STATUS_SUCCESS = "success"
ACTION_STEP_STATUS_FAILED = "failed"

POST_APPROVAL_CHAIN_CODE = "post_approval_followup"


@dataclass(frozen=True, slots=True)
class ActionChainStepDefinition:
    step_code: str
    tool_name: str
    reason: str
    output_key: str


POST_APPROVAL_TOOL_CHAIN: tuple[ActionChainStepDefinition, ...] = (
    ActionChainStepDefinition(
        step_code="create_task",
        tool_name="task.create_from_approval",
        reason="审批通过后先生成正式销售任务，确保后续动作有稳定的业务主键。",
        output_key="task",
    ),
    ActionChainStepDefinition(
        step_code="send_notification",
        tool_name="notify.send_task_assignment",
        reason="任务生成后立即通知负责人，避免 AI 建议停留在系统内无人认领。",
        output_key="notification",
    ),
    ActionChainStepDefinition(
        step_code="create_calendar_event",
        tool_name="calendar.create_follow_up_event",
        reason="通知后同步创建跟进日程，占住执行时间窗口。",
        output_key="calendar_event",
    ),
)

_STEP_BY_CODE = {item.step_code: item for item in POST_APPROVAL_TOOL_CHAIN}


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_to_json_safe(item) for item in value]
    return value


def _dumps_json(value: dict[str, Any]) -> str:
    return json.dumps(_to_json_safe(value), ensure_ascii=False)


def _serialize_row_datetime(row: dict[str, Any], *field_names: str) -> dict[str, Any]:
    result = dict(row)
    for field_name in field_names:
        value = result.get(field_name)
        result[field_name] = value.isoformat() if value else None
    return result


def _normalize_runtime_payload_for_execution(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_payload = copy.deepcopy(payload)
    happened_at = runtime_payload.get("happened_at")
    if isinstance(happened_at, str):
        try:
            runtime_payload["happened_at"] = datetime.fromisoformat(happened_at)
        except ValueError:
            runtime_payload["happened_at"] = None
    return runtime_payload


def _build_step_execution_record(
    step: ActionChainStepDefinition,
    *,
    execution: dict[str, Any] | None,
    status: str,
    retry_count: int,
    error_message: str | None = None,
) -> dict[str, Any]:
    if execution:
        return {
            "step_code": step.step_code,
            "tool_name": execution["tool_name"],
            "server_name": execution["server_name"],
            "protocol": execution["protocol"],
            "reason": step.reason,
            "audit_record": execution["audit_record"],
            "output": execution["output"],
            "status": status,
            "retry_count": retry_count,
            "error_message": error_message,
        }
    server_name, _, _ = step.tool_name.partition(".")
    return {
        "step_code": step.step_code,
        "tool_name": step.tool_name,
        "server_name": server_name,
        "protocol": "mcp",
        "reason": step.reason,
        "audit_record": None,
        "output": None,
        "status": status,
        "retry_count": retry_count,
        "error_message": error_message,
    }


def _load_action_run_row(db: Session, *, tenant_id: str, action_run_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT action_run_id, tenant_id, chain_code, approval_id, customer_id, trigger_source,
                   triggered_by_user_id, status, current_step_code, context_payload_json,
                   error_message, created_at, finished_at
            FROM agent_action_run
            WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "action_run_id": action_run_id},
    ).mappings().first()
    if not row:
        raise LookupError("动作链运行记录不存在")
    result = _serialize_row_datetime(dict(row), "created_at", "finished_at")
    result["context_payload_json"] = _loads_json(result.get("context_payload_json"))
    return result


def _load_action_run_steps(db: Session, *, tenant_id: str, action_run_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT step_run_id, action_run_id, approval_id, customer_id, step_code, tool_name,
                   step_order, status, input_payload_json, output_payload_json, error_message,
                   retry_count, started_at, finished_at, created_at
            FROM agent_action_run_step
            WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id
            ORDER BY step_order ASC
            """
        ),
        {"tenant_id": tenant_id, "action_run_id": action_run_id},
    ).mappings().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_row_datetime(dict(row), "started_at", "finished_at", "created_at")
        item["input_payload_json"] = _loads_json(item.get("input_payload_json"))
        item["output_payload_json"] = _loads_json(item.get("output_payload_json"))
        items.append(item)
    return items


def _upsert_action_run_step(
    db: Session,
    *,
    tenant_id: str,
    action_run_id: str,
    approval_id: str | None,
    customer_id: str | None,
    step: ActionChainStepDefinition,
    step_order: int,
    input_payload: dict[str, Any],
    retry_count: int,
    status: str,
    output_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    existing = db.execute(
        text(
            """
            SELECT step_run_id
            FROM agent_action_run_step
            WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id AND step_code = :step_code
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "action_run_id": action_run_id,
            "step_code": step.step_code,
        },
    ).scalar_one_or_none()
    if existing:
        db.execute(
            text(
                """
                UPDATE agent_action_run_step
                SET tool_name = :tool_name,
                    step_order = :step_order,
                    status = :status,
                    input_payload_json = :input_payload_json,
                    output_payload_json = :output_payload_json,
                    error_message = :error_message,
                    retry_count = :retry_count,
                    started_at = :started_at,
                    finished_at = :finished_at
                WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id AND step_code = :step_code
                """
            ),
            {
                "tenant_id": tenant_id,
                "action_run_id": action_run_id,
                "step_code": step.step_code,
                "tool_name": step.tool_name,
                "step_order": step_order,
                "status": status,
                "input_payload_json": _dumps_json(input_payload),
                "output_payload_json": _dumps_json(output_payload or {}) if output_payload else None,
                "error_message": error_message,
                "retry_count": retry_count,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )
        return
    db.execute(
        text(
            """
            INSERT INTO agent_action_run_step (
              tenant_id, step_run_id, action_run_id, approval_id, customer_id, step_code,
              tool_name, step_order, status, input_payload_json, output_payload_json,
              error_message, retry_count, started_at, finished_at
            )
            VALUES (
              :tenant_id, :step_run_id, :action_run_id, :approval_id, :customer_id, :step_code,
              :tool_name, :step_order, :status, :input_payload_json, :output_payload_json,
              :error_message, :retry_count, :started_at, :finished_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "step_run_id": new_id("astep"),
            "action_run_id": action_run_id,
            "approval_id": approval_id,
            "customer_id": customer_id,
            "step_code": step.step_code,
            "tool_name": step.tool_name,
            "step_order": step_order,
            "status": status,
            "input_payload_json": _dumps_json(input_payload),
            "output_payload_json": _dumps_json(output_payload or {}) if output_payload else None,
            "error_message": error_message,
            "retry_count": retry_count,
            "started_at": started_at,
            "finished_at": finished_at,
        },
    )


def _create_action_run(
    db: Session,
    *,
    tenant_id: str,
    approval_id: str | None,
    customer_id: str | None,
    current_user: dict[str, Any],
    runtime_payload: dict[str, Any],
) -> str:
    action_run_id = new_id("arun")
    first_step = POST_APPROVAL_TOOL_CHAIN[0].step_code if POST_APPROVAL_TOOL_CHAIN else None
    db.execute(
        text(
            """
            INSERT INTO agent_action_run (
              tenant_id, action_run_id, chain_code, approval_id, customer_id, trigger_source,
              triggered_by_user_id, status, current_step_code, context_payload_json
            )
            VALUES (
              :tenant_id, :action_run_id, :chain_code, :approval_id, :customer_id, 'approval',
              :triggered_by_user_id, :status, :current_step_code, :context_payload_json
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "action_run_id": action_run_id,
            "chain_code": POST_APPROVAL_CHAIN_CODE,
            "approval_id": approval_id,
            "customer_id": customer_id,
            "triggered_by_user_id": current_user["user_id"],
            "status": ACTION_RUN_STATUS_RUNNING,
            "current_step_code": first_step,
            "context_payload_json": _dumps_json(runtime_payload),
        },
    )
    return action_run_id


def _update_action_run_state(
    db: Session,
    *,
    tenant_id: str,
    action_run_id: str,
    status: str,
    current_step_code: str | None,
    runtime_payload: dict[str, Any],
    error_message: str | None = None,
    finished_at: datetime | None = None,
) -> None:
    db.execute(
        text(
            """
            UPDATE agent_action_run
            SET status = :status,
                current_step_code = :current_step_code,
                context_payload_json = :context_payload_json,
                error_message = :error_message,
                finished_at = :finished_at
            WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "action_run_id": action_run_id,
            "status": status,
            "current_step_code": current_step_code,
            "context_payload_json": _dumps_json(runtime_payload),
            "error_message": error_message,
            "finished_at": finished_at,
        },
    )


def _build_action_run_result(db: Session, *, tenant_id: str, action_run_id: str) -> dict[str, Any]:
    run_row = _load_action_run_row(db, tenant_id=tenant_id, action_run_id=action_run_id)
    steps = _load_action_run_steps(db, tenant_id=tenant_id, action_run_id=action_run_id)
    runtime_payload = run_row.get("context_payload_json") or {}
    tool_executions = [
        item["output_payload_json"]
        if item.get("output_payload_json")
        else _build_step_execution_record(
            _STEP_BY_CODE[item["step_code"]],
            execution=None,
            status=item["status"],
            retry_count=int(item.get("retry_count") or 0),
            error_message=item.get("error_message"),
        )
        for item in steps
    ]
    return {
        "action_run_id": run_row["action_run_id"],
        "chain_code": run_row["chain_code"],
        "status": run_row["status"],
        "current_step_code": run_row.get("current_step_code"),
        "error_message": run_row.get("error_message"),
        "approval_id": run_row.get("approval_id"),
        "customer_id": run_row.get("customer_id"),
        "task_id": (runtime_payload.get("task") or {}).get("task_id"),
        "task": runtime_payload.get("task"),
        "notification": runtime_payload.get("notification"),
        "calendar_event": runtime_payload.get("calendar_event"),
        "tool_executions": tool_executions,
        "steps": steps,
        "created_at": run_row.get("created_at"),
        "finished_at": run_row.get("finished_at"),
        "can_retry": run_row["status"] == ACTION_RUN_STATUS_FAILED,
    }


def _execute_action_chain(
    db: Session,
    *,
    current_user: dict[str, Any],
    action_run_id: str,
    runtime_payload: dict[str, Any],
    start_step_code: str,
) -> dict[str, Any]:
    gateway = build_shared_mcp_gateway()
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id=runtime_payload.get("approval", {}).get("run_id") or f"approval_{runtime_payload['approval']['approval_id']}",
        db=db,
    )
    start_index = next(
        (index for index, item in enumerate(POST_APPROVAL_TOOL_CHAIN) if item.step_code == start_step_code),
        None,
    )
    if start_index is None:
        raise ValueError(f"无法找到动作链步骤: {start_step_code}")

    approval = runtime_payload.get("approval") or {}
    tenant_id = current_user["tenant_id"]

    for step_order, step in enumerate(POST_APPROVAL_TOOL_CHAIN[start_index:], start=start_index + 1):
        started_at = datetime.now()
        input_payload = _to_json_safe(runtime_payload)
        existing_step = db.execute(
            text(
                """
                SELECT retry_count
                FROM agent_action_run_step
                WHERE tenant_id = :tenant_id AND action_run_id = :action_run_id AND step_code = :step_code
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "action_run_id": action_run_id,
                "step_code": step.step_code,
            },
        ).mappings().first()
        retry_count = int((existing_step or {}).get("retry_count") or 0) + 1
        _upsert_action_run_step(
            db,
            tenant_id=tenant_id,
            action_run_id=action_run_id,
            approval_id=approval.get("approval_id"),
            customer_id=approval.get("customer_id"),
            step=step,
            step_order=step_order,
            input_payload=input_payload,
            retry_count=retry_count,
            status=ACTION_STEP_STATUS_RUNNING,
            started_at=started_at,
            finished_at=None,
        )
        _update_action_run_state(
            db,
            tenant_id=tenant_id,
            action_run_id=action_run_id,
            status=ACTION_RUN_STATUS_RUNNING,
            current_step_code=step.step_code,
            runtime_payload=runtime_payload,
            error_message=None,
            finished_at=None,
        )
        try:
            execution = gateway.execute(step.tool_name, context, runtime_payload)
        except Exception as exc:
            record = _build_step_execution_record(
                step,
                execution=None,
                status=ACTION_STEP_STATUS_FAILED,
                retry_count=retry_count,
                error_message=str(exc),
            )
            _upsert_action_run_step(
                db,
                tenant_id=tenant_id,
                action_run_id=action_run_id,
                approval_id=approval.get("approval_id"),
                customer_id=approval.get("customer_id"),
                step=step,
                step_order=step_order,
                input_payload=input_payload,
                retry_count=retry_count,
                status=ACTION_STEP_STATUS_FAILED,
                output_payload=record,
                error_message=str(exc),
                started_at=started_at,
                finished_at=datetime.now(),
            )
            _update_action_run_state(
                db,
                tenant_id=tenant_id,
                action_run_id=action_run_id,
                status=ACTION_RUN_STATUS_FAILED,
                current_step_code=step.step_code,
                runtime_payload=runtime_payload,
                error_message=str(exc),
                finished_at=datetime.now(),
            )
            return _build_action_run_result(db, tenant_id=tenant_id, action_run_id=action_run_id)

        record = _build_step_execution_record(
            step,
            execution=execution,
            status=ACTION_STEP_STATUS_SUCCESS,
            retry_count=retry_count,
        )
        runtime_payload[step.output_key] = execution["output"]
        _upsert_action_run_step(
            db,
            tenant_id=tenant_id,
            action_run_id=action_run_id,
            approval_id=approval.get("approval_id"),
            customer_id=approval.get("customer_id"),
            step=step,
            step_order=step_order,
            input_payload=input_payload,
            retry_count=retry_count,
            status=ACTION_STEP_STATUS_SUCCESS,
            output_payload=record,
            error_message=None,
            started_at=started_at,
            finished_at=datetime.now(),
        )

    _update_action_run_state(
        db,
        tenant_id=tenant_id,
        action_run_id=action_run_id,
        status=ACTION_RUN_STATUS_SUCCESS,
        current_step_code=None,
        runtime_payload=runtime_payload,
        error_message=None,
        finished_at=datetime.now(),
    )
    return _build_action_run_result(db, tenant_id=tenant_id, action_run_id=action_run_id)


def execute_post_approval_action_flow(
    db: Session,
    *,
    current_user: dict[str, Any],
    approval: dict[str, Any],
    proposed_payload: dict[str, Any],
    happened_at: datetime | None = None,
) -> dict[str, Any]:
    """中文注释：审批通过后启动统一动作链，并把每一步状态沉淀为可恢复的运行记录。"""

    runtime_payload = _normalize_runtime_payload_for_execution(
        {
            "approval": approval,
            "proposed_payload": proposed_payload,
            "happened_at": happened_at,
        }
    )
    action_run_id = _create_action_run(
        db,
        tenant_id=current_user["tenant_id"],
        approval_id=approval.get("approval_id"),
        customer_id=approval.get("customer_id"),
        current_user=current_user,
        runtime_payload=runtime_payload,
    )
    return _execute_action_chain(
        db,
        current_user=current_user,
        action_run_id=action_run_id,
        runtime_payload=runtime_payload,
        start_step_code=POST_APPROVAL_TOOL_CHAIN[0].step_code,
    )


def retry_post_approval_action_run(
    db: Session,
    *,
    current_user: dict[str, Any],
    action_run_id: str,
) -> dict[str, Any]:
    """中文注释：从失败步骤继续执行动作链，已成功的步骤不再重复执行。"""

    run_row = _load_action_run_row(db, tenant_id=current_user["tenant_id"], action_run_id=action_run_id)
    if run_row["status"] != ACTION_RUN_STATUS_FAILED:
        raise ValueError("当前动作链不处于失败状态，无需重试")
    runtime_payload = _normalize_runtime_payload_for_execution(run_row.get("context_payload_json") or {})
    if not isinstance(runtime_payload.get("approval"), dict) or not isinstance(runtime_payload.get("proposed_payload"), dict):
        raise ValueError("动作链上下文不完整，无法继续执行")
    start_step_code = run_row.get("current_step_code")
    if not start_step_code:
        failed_step = next(
            (
                item["step_code"]
                for item in _load_action_run_steps(
                    db,
                    tenant_id=current_user["tenant_id"],
                    action_run_id=action_run_id,
                )
                if item["status"] == ACTION_STEP_STATUS_FAILED
            ),
            None,
        )
        if not failed_step:
            raise ValueError("未找到需要重试的失败步骤")
        start_step_code = failed_step
    return _execute_action_chain(
        db,
        current_user=current_user,
        action_run_id=action_run_id,
        runtime_payload=runtime_payload,
        start_step_code=start_step_code,
    )


def get_post_approval_action_run_detail(
    db: Session,
    *,
    current_user: dict[str, Any],
    action_run_id: str,
) -> dict[str, Any]:
    return _build_action_run_result(db, tenant_id=current_user["tenant_id"], action_run_id=action_run_id)


def list_failed_post_approval_action_runs(
    db: Session,
    *,
    current_user: dict[str, Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT action_run_id, chain_code, approval_id, customer_id, trigger_source,
                   triggered_by_user_id, status, current_step_code, context_payload_json,
                   error_message, created_at, finished_at
            FROM agent_action_run
            WHERE tenant_id = :tenant_id
              AND status = :status
            ORDER BY COALESCE(finished_at, created_at) DESC, created_at DESC
            LIMIT :limit
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "status": ACTION_RUN_STATUS_FAILED,
            "limit": max(1, min(limit, 100)),
        },
    ).mappings().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_row_datetime(dict(row), "created_at", "finished_at")
        context_payload = _loads_json(item.get("context_payload_json"))
        item["task_id"] = (context_payload.get("task") or {}).get("task_id")
        item["can_retry"] = True
        item.pop("context_payload_json", None)
        items.append(item)
    return items
