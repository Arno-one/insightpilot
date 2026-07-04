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


def _build_template_plan(handler: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    """基于已识别 handler 生成稳定模板计划，避免 V1 过早依赖不确定的 LLM Planner 输出。"""
    intent = (input_payload.get("intent_route") or {}).get("intent") or "unknown"
    question = input_payload.get("question") or ""
    templates: dict[str, list[dict[str, Any]]] = {
        "followup.plan_strategy": [
            {"step_code": "load_context", "title": "读取客户上下文", "tool_name": "customer.context"},
            {"step_code": "build_strategy", "title": "生成跟进策略", "tool_name": "followup.plan_strategy"},
            {"step_code": "summarize_reply", "title": "汇总可读回复", "tool_name": "agent.coordinator"},
        ],
        "data.query_sql": [
            {"step_code": "understand_question", "title": "理解数据问题", "tool_name": "intent_router"},
            {"step_code": "generate_sql", "title": "生成并校验 SQL", "tool_name": "data.query_sql"},
            {"step_code": "summarize_result", "title": "汇总查询结果", "tool_name": "agent.coordinator"},
        ],
        "data.analyze_business": [
            {"step_code": "prepare_query", "title": "准备经营分析查询", "tool_name": "data.query_sql"},
            {"step_code": "analyze_rows", "title": "分析经营数据", "tool_name": "data.analyze_business"},
            {"step_code": "summarize_insight", "title": "汇总结论和建议", "tool_name": "agent.coordinator"},
        ],
    }
    steps = templates.get(
        handler,
        [
            {"step_code": "understand_task", "title": "理解任务", "tool_name": "intent_router"},
            {"step_code": "execute_handler", "title": f"调用 {handler}", "tool_name": handler},
            {"step_code": "summarize_reply", "title": "汇总回复", "tool_name": "agent.coordinator"},
        ],
    )
    planned_steps = [
        {
            **step,
            "step_order": index + 1,
            "depends_on": [steps[index - 1]["step_code"]] if index else [],
        }
        for index, step in enumerate(steps)
    ]
    return {
        "planner": "template_planner_v1",
        "intent": intent,
        "handler": handler,
        "objective": str(question)[:1000],
        "summary": " -> ".join(step["title"] for step in planned_steps),
        "steps": planned_steps,
    }


def _build_runtime_step_queue(
    *,
    handler: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    status: str,
    error_message: str | None = None,
) -> list[dict[str, Any]]:
    """构造统一对话 Runtime 的顺序步骤队列，V1 先覆盖路由和工具执行两个内部节点。"""
    route_input = {
        "session_id": input_payload.get("session_id"),
        "message_id": input_payload.get("message_id"),
        "question": input_payload.get("question"),
    }
    route_output = {
        "intent_route": input_payload.get("intent_route"),
        "selected_handler": handler,
    }
    plan = _build_template_plan(handler, input_payload)
    return [
        {
            "step_id": new_id("step"),
            "step_code": "intent_route",
            "step_order": 1,
            "node_name": "agent_chat_intent_route",
            "tool_name": "intent_router",
            "step_title": "识别统一对话意图",
            "step_type": "planner",
            "depends_on": [],
            "input_payload": route_input,
            "output_payload": route_output,
            "status": "success",
            "error_message": None,
        },
        {
            "step_id": new_id("step"),
            "step_code": "template_planner",
            "step_order": 2,
            "node_name": "agent_chat_planner",
            "tool_name": "template_planner_v1",
            "step_title": "生成结构化执行计划",
            "step_type": "planner",
            "depends_on": ["intent_route"],
            "input_payload": route_output,
            "output_payload": plan,
            "status": "success",
            "error_message": None,
        },
        {
            "step_id": new_id("step"),
            "step_code": "tool_handler",
            "step_order": 3,
            "node_name": "agent_chat_tool",
            "tool_name": str(handler)[:80],
            "step_title": f"调用 {handler} 处理统一对话请求"[:120],
            "step_type": "tool_call",
            "depends_on": ["template_planner"],
            "input_payload": input_payload,
            "output_payload": output_payload,
            "status": status,
            "error_message": error_message[:1000] if error_message else None,
        },
    ]


def _insert_runtime_steps(
    db: Session,
    *,
    tenant_id: str,
    run_id: str,
    step_records: list[dict[str, Any]],
    started_at: datetime,
    finished_at: datetime,
) -> None:
    """按顺序写入 Agent Step，让 Trace 从单工具记录升级为多步骤链路。"""
    for record in step_records:
        db.execute(
            text(
                """
                INSERT INTO agent_step (
                  tenant_id, step_id, run_id, node_name, tool_name, input_json, output_json,
                  status, error_message, started_at, finished_at, duration_ms
                )
                VALUES (
                  :tenant_id, :step_id, :run_id, :node_name, :tool_name, :input_json, :output_json,
                  :status, :error_message, :started_at, :finished_at, 0
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "step_id": record["step_id"],
                "run_id": run_id,
                "node_name": record["node_name"],
                "tool_name": record["tool_name"],
                "input_json": _dumps(record["input_payload"]),
                "output_json": _dumps(record["output_payload"]),
                "status": record["status"],
                "error_message": record.get("error_message"),
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )


def _insert_runtime_plan(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    run_id: str,
    handler: str,
    status: str,
    step_records: list[dict[str, Any]],
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    """为 Runtime 步骤队列生成计划结构，计划步骤与真实 Agent Step 一一关联。"""
    plan_id = new_id("plan")
    now = datetime.now()
    question = str(input_payload.get("question") or "")[:1000]

    db.execute(
        text(
            """
            INSERT INTO agent_run_plan (
              tenant_id, plan_id, run_id, user_id, plan_type, plan_title, objective_summary,
              status, source_intent, planned_at, started_at, finished_at, metadata_json
            )
            VALUES (
              :tenant_id, :plan_id, :run_id, :user_id, 'multi_step',
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
            "metadata_json": _dumps(
                {
                    "runtime_handler": handler,
                    "runtime_version": "agent_chat_runtime_v1",
                    "step_count": len(step_records),
                }
            ),
        },
    )
    plan_step_ids: list[str] = []
    for record in step_records:
        plan_step_id = new_id("pstep")
        output_summary = record.get("error_message") or record["output_payload"].get("handler") or record["tool_name"]
        db.execute(
            text(
                """
                INSERT INTO agent_run_plan_step (
                  tenant_id, plan_step_id, plan_id, run_id, step_code, step_order, step_title,
                  step_type, tool_name, depends_on_json, status, input_summary, output_summary,
                  linked_step_id, error_message, metadata_json
                )
                VALUES (
                  :tenant_id, :plan_step_id, :plan_id, :run_id, :step_code, :step_order,
                  :step_title, :step_type, :tool_name, :depends_on_json, :status,
                  :input_summary, :output_summary, :linked_step_id, :error_message, :metadata_json
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "plan_step_id": plan_step_id,
                "plan_id": plan_id,
                "run_id": run_id,
                "step_code": record["step_code"],
                "step_order": record["step_order"],
                "step_title": record["step_title"],
                "step_type": record["step_type"],
                "tool_name": record["tool_name"],
                "depends_on_json": _dumps(record["depends_on"]),
                "status": record["status"],
                "input_summary": question,
                "output_summary": str(output_summary or "")[:1000],
                "linked_step_id": record["step_id"],
                "error_message": record.get("error_message"),
                "metadata_json": _dumps({"source": "agent_chat_runtime_step_queue"}),
            },
        )
        plan_step_ids.append(plan_step_id)
    return {"plan_id": plan_id, "plan_step_id": plan_step_ids[-1], "plan_step_ids": plan_step_ids}


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
    step_records = _build_runtime_step_queue(
        handler=str(handler),
        input_payload=input_payload,
        output_payload=output_payload,
        status="success",
    )
    step_id = step_records[-1]["step_id"]
    planner_plan = step_records[1]["output_payload"]

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
    _insert_runtime_steps(
        db,
        tenant_id=tenant_id,
        run_id=run_id,
        step_records=step_records,
        started_at=now,
        finished_at=now,
    )
    plan_result = _insert_runtime_plan(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        run_id=run_id,
        handler=str(handler),
        status="success",
        step_records=step_records,
        input_payload=input_payload,
    )
    step_ids = [record["step_id"] for record in step_records]

    metadata = {
        **_loads_json(assistant_message.get("metadata_json")),
        "runtime_run_id": run_id,
        "runtime_step_id": step_id,
        "runtime_step_ids": step_ids,
        "runtime_plan_id": plan_result["plan_id"],
        "runtime_plan_step_id": plan_result["plan_step_id"],
        "runtime_plan_step_ids": plan_result["plan_step_ids"],
        "runtime_planner": planner_plan,
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
    return {"run_id": run_id, "step_id": step_id, "step_ids": step_ids, "planner": planner_plan, **plan_result}


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
    step_records = _build_runtime_step_queue(
        handler=handler,
        input_payload=input_payload,
        output_payload=output_payload,
        status="failed",
        error_message=error_message,
    )
    step_id = step_records[-1]["step_id"]
    planner_plan = step_records[1]["output_payload"]

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
    _insert_runtime_steps(
        db,
        tenant_id=tenant_id,
        run_id=run_id,
        step_records=step_records,
        started_at=now,
        finished_at=now,
    )
    plan_result = _insert_runtime_plan(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        run_id=run_id,
        handler=handler,
        status="failed",
        step_records=step_records,
        input_payload=input_payload,
    )
    step_ids = [record["step_id"] for record in step_records]

    metadata = {
        **_loads_json(assistant_message.get("metadata_json")),
        "runtime_run_id": run_id,
        "runtime_step_id": step_id,
        "runtime_step_ids": step_ids,
        "runtime_plan_id": plan_result["plan_id"],
        "runtime_plan_step_id": plan_result["plan_step_id"],
        "runtime_plan_step_ids": plan_result["plan_step_ids"],
        "runtime_planner": planner_plan,
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
    return {"run_id": run_id, "step_id": step_id, "step_ids": step_ids, "planner": planner_plan, **plan_result}
