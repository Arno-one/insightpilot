from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


def _loads_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    return json.loads(value)


def _insert_runtime_plan(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    run_id: str,
    step_id: str,
    handler: str,
    status: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    error_message: str | None = None,
) -> dict[str, str]:
    """为当前单步 Runtime 生成可演进的执行计划，后续多步编排直接复用同一结构。"""
    plan_id = new_id("plan")
    plan_step_id = new_id("pstep")
    now = datetime.now()
    question = str(input_payload.get("question") or "")[:1000]
    output_summary = error_message or output_payload.get("handler") or handler

    db.execute(
        text(
            """
            INSERT INTO agent_run_plan (
              tenant_id, plan_id, run_id, user_id, plan_type, plan_title, objective_summary,
              status, source_intent, planned_at, started_at, finished_at, metadata_json
            )
            VALUES (
              :tenant_id, :plan_id, :run_id, :user_id, 'single_tool',
              '统一对话工具运行计划', :objective_summary, :status, :source_intent,
              :planned_at, :started_at, :finished_at, :metadata_json
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "plan_id": plan_id,
            "run_id": run_id,
            "user_id": user_id,
            "objective_summary": question,
            "status": status,
            "source_intent": (input_payload.get("intent_route") or {}).get("intent"),
            "planned_at": now,
            "started_at": now,
            "finished_at": now,
            "metadata_json": _dumps({"runtime_handler": handler, "runtime_version": "agent_chat_runtime_v1"}),
        },
    )
    db.execute(
        text(
            """
            INSERT INTO agent_run_plan_step (
              tenant_id, plan_step_id, plan_id, run_id, step_code, step_order, step_title,
              step_type, tool_name, depends_on_json, status, input_summary, output_summary,
              linked_step_id, error_message, metadata_json
            )
            VALUES (
              :tenant_id, :plan_step_id, :plan_id, :run_id, 'agent_chat_tool', 1,
              :step_title, 'tool_call', :tool_name, :depends_on_json, :status,
              :input_summary, :output_summary, :linked_step_id, :error_message, :metadata_json
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "plan_step_id": plan_step_id,
            "plan_id": plan_id,
            "run_id": run_id,
            "step_title": f"调用 {handler} 处理统一对话请求"[:120],
            "tool_name": str(handler)[:80],
            "depends_on_json": _dumps([]),
            "status": status,
            "input_summary": question,
            "output_summary": str(output_summary or "")[:1000],
            "linked_step_id": step_id,
            "error_message": error_message[:1000] if error_message else None,
            "metadata_json": _dumps({"source": "agent_chat_runtime_trace", "linked_step_id": step_id}),
        },
    )
    return {"plan_id": plan_id, "plan_step_id": plan_step_id}


def record_successful_runtime_trace(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    user_message: dict[str, Any],
    assistant_message: dict[str, Any],
    intent_route: dict[str, Any],
    runtime_result: dict[str, Any],
) -> dict[str, Any]:
    """把统一 Agent Chat 的一次工具运行写入 Agent Run/Step，并回写助手消息 run_id。"""
    run_id = new_id("run")
    step_id = new_id("step")
    now = datetime.now()
    handler = runtime_result.get("handler") or assistant_message.get("tool_name") or "agent_chat_runtime"
    input_payload = {
        "session_id": session_id,
        "message_id": user_message.get("message_id"),
        "question": user_message.get("content"),
        "intent_route": intent_route,
    }
    output_payload = {
        "session_id": session_id,
        "message_id": assistant_message.get("message_id"),
        "handler": handler,
        "tool_name": assistant_message.get("tool_name"),
        "runtime": runtime_result,
    }

    db.execute(
        text(
            """
            INSERT INTO agent_run (
              tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json,
              status, started_at, finished_at, total_duration_ms
            )
            VALUES (
              :tenant_id, :run_id, :user_id, 'agent_chat_runtime', 'unified_agent_chat_runtime',
              :input_json, :output_json, 'success', :started_at, :finished_at, 0
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "user_id": user_id,
            "input_json": _dumps(input_payload),
            "output_json": _dumps(output_payload),
            "started_at": now,
            "finished_at": now,
        },
    )
    db.execute(
        text(
            """
            INSERT INTO agent_step (
              tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
              status, started_at, finished_at, duration_ms
            )
            VALUES (
              :tenant_id, :step_id, :run_id, :node_name, :tool_name, :input_json, :output_json,
              'success', :started_at, :finished_at, 0
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "step_id": step_id,
            "run_id": run_id,
            "node_name": "agent_chat_tool",
            "tool_name": str(handler)[:80],
            "input_json": _dumps(input_payload),
            "output_json": _dumps(output_payload),
            "started_at": now,
            "finished_at": now,
        },
    )
    plan_result = _insert_runtime_plan(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        run_id=run_id,
        step_id=step_id,
        handler=str(handler),
        status="success",
        input_payload=input_payload,
        output_payload=output_payload,
    )

    metadata = {
        **_loads_json(assistant_message.get("metadata_json")),
        "runtime_run_id": run_id,
        "runtime_step_id": step_id,
        "runtime_plan_id": plan_result["plan_id"],
        "runtime_plan_step_id": plan_result["plan_step_id"],
    }
    db.execute(
        text(
            """
            UPDATE agent_chat_message
            SET run_id = :run_id,
                metadata_json = :metadata_json
            WHERE tenant_id = :tenant_id
              AND message_id = :message_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "message_id": assistant_message["message_id"],
            "run_id": run_id,
            "metadata_json": _dumps(metadata),
        },
    )
    assistant_message["run_id"] = run_id
    assistant_message["metadata_json"] = metadata
    db.commit()
    return {"run_id": run_id, "step_id": step_id, **plan_result}


def record_failed_runtime_trace(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    user_message: dict[str, Any],
    assistant_message: dict[str, Any],
    intent_route: dict[str, Any],
    handler: str,
    error_message: str,
    recovery_plan: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """记录统一 Agent Chat 工具失败，保证失败也能进入 Trace 审计链。"""
    run_id = new_id("run")
    step_id = new_id("step")
    now = datetime.now()
    input_payload = {
        "session_id": session_id,
        "message_id": user_message.get("message_id"),
        "question": user_message.get("content"),
        "intent_route": intent_route,
    }
    output_payload = {
        "session_id": session_id,
        "message_id": assistant_message.get("message_id"),
        "handler": handler,
        "tool_name": assistant_message.get("tool_name"),
        "error": error_message,
        "recovery_plan": recovery_plan or [],
    }

    db.execute(
        text(
            """
            INSERT INTO agent_run (
              tenant_id, run_id, user_id, run_type, graph_name, input_json, output_json,
              status, error_message, started_at, finished_at, total_duration_ms
            )
            VALUES (
              :tenant_id, :run_id, :user_id, 'agent_chat_runtime', 'unified_agent_chat_runtime',
              :input_json, :output_json, 'failed', :error_message, :started_at, :finished_at, 0
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "user_id": user_id,
            "input_json": _dumps(input_payload),
            "output_json": _dumps(output_payload),
            "error_message": error_message[:1000],
            "started_at": now,
            "finished_at": now,
        },
    )
    db.execute(
        text(
            """
            INSERT INTO agent_step (
              tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
              status, error_message, started_at, finished_at, duration_ms
            )
            VALUES (
              :tenant_id, :step_id, :run_id, 'agent_chat_tool', :tool_name, :input_json, :output_json,
              'failed', :error_message, :started_at, :finished_at, 0
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "step_id": step_id,
            "run_id": run_id,
            "tool_name": str(handler)[:80],
            "input_json": _dumps(input_payload),
            "output_json": _dumps(output_payload),
            "error_message": error_message[:1000],
            "started_at": now,
            "finished_at": now,
        },
    )
    plan_result = _insert_runtime_plan(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        run_id=run_id,
        step_id=step_id,
        handler=handler,
        status="failed",
        input_payload=input_payload,
        output_payload=output_payload,
        error_message=error_message,
    )

    metadata = {
        **_loads_json(assistant_message.get("metadata_json")),
        "runtime_run_id": run_id,
        "runtime_step_id": step_id,
        "runtime_plan_id": plan_result["plan_id"],
        "runtime_plan_step_id": plan_result["plan_step_id"],
        "runtime_status": "failed",
        "runtime_error": error_message,
        "recovery_plan": recovery_plan or [],
    }
    db.execute(
        text(
            """
            UPDATE agent_chat_message
            SET run_id = :run_id,
                metadata_json = :metadata_json
            WHERE tenant_id = :tenant_id
              AND message_id = :message_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "message_id": assistant_message["message_id"],
            "run_id": run_id,
            "metadata_json": _dumps(metadata),
        },
    )
    assistant_message["run_id"] = run_id
    assistant_message["metadata_json"] = metadata
    db.commit()
    return {"run_id": run_id, "step_id": step_id, **plan_result}
