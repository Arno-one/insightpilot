import json
import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.database import get_db, get_readonly_db
from app.modules.agent import (
    chat_session_service,
    chat_runtime_trace_service,
    conversation_memory_service,
    customer_profile_tool,
    data_analyst_tool,
    execution_tool,
    followup_strategy_tool,
    intent_router,
    manager_tool,
    memory_service,
    nl2sql_tool,
    opportunity_tool,
)
from app.modules.agent.platform import list_agent_chat_tool_specs, route_agent_chat_tool
from app.modules.agent.schemas import (
    AgentChatIntentRouteRequest,
    AgentChatMessageCreateRequest,
    AgentChatRecoveryActionEventRequest,
    AgentChatSessionCreateRequest,
    RiskChatMessageRequest,
)
from app.modules.auth.dependencies import require_permission
from app.modules.crm import service as crm_service
from app.modules.llm.client import generate_risk_chat_reply
from app.shared.response import success

router = APIRouter()


def _loads_json(value):
    """兼容 MySQL JSON 字段返回字符串或原生 dict/list 的情况。"""
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return value


def _collect_trace_ids_from_step(step: dict) -> list[str]:
    """从 Agent Step 输出中提取 RAG trace_id，便于详情页串起检索链路。"""
    trace_ids: list[str] = []
    output = step.get("output_json")
    if isinstance(output, dict):
        if output.get("trace_id"):
            trace_ids.append(output["trace_id"])
        for trace_id in output.get("trace_ids", []):
            if trace_id:
                trace_ids.append(trace_id)
    return trace_ids


def _load_action_run_bundles(db: Session, tenant_id: str, approval_ids: list[str]) -> list[dict]:
    if not approval_ids:
        return []
    run_rows = db.execute(
        text(
            """
            SELECT action_run_id, chain_code, approval_id, customer_id, trigger_source,
                   triggered_by_user_id, status, current_step_code, context_payload_json,
                   error_message, created_at, finished_at
            FROM agent_action_run
            WHERE tenant_id = :tenant_id
              AND approval_id IN :approval_ids
            ORDER BY created_at DESC
            """
        ).bindparams(bindparam("approval_ids", expanding=True)),
        {"tenant_id": tenant_id, "approval_ids": approval_ids},
    ).mappings().all()
    items: list[dict] = []
    for row in run_rows:
        run_item = dict(row)
        run_item["context_payload_json"] = _loads_json(run_item.get("context_payload_json"))
        step_rows = db.execute(
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
            {"tenant_id": tenant_id, "action_run_id": run_item["action_run_id"]},
        ).mappings().all()
        steps = []
        for step_row in step_rows:
            step = dict(step_row)
            step["input_payload_json"] = _loads_json(step.get("input_payload_json"))
            step["output_payload_json"] = _loads_json(step.get("output_payload_json"))
            steps.append(step)
        items.append(
            {
                **run_item,
                "task_id": (run_item.get("context_payload_json") or {}).get("task", {}).get("task_id"),
                "notification_id": (run_item.get("context_payload_json") or {}).get("notification", {}).get(
                    "notification_id"
                ),
                "can_retry": run_item.get("status") == "failed",
                "steps": steps,
            }
        )
    return items


def _load_agent_run_plans(db: Session, tenant_id: str, run_id: str) -> list[dict]:
    """加载 Agent Run 关联的执行计划，供 Trace 详情页和后续编排视图复用。"""
    plan_rows = db.execute(
        text(
            """
            SELECT plan_id, run_id, user_id, plan_type, plan_title, objective_summary,
                   status, source_intent, planned_at, started_at, finished_at,
                   metadata_json, created_at, updated_at
            FROM agent_run_plan
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            ORDER BY planned_at ASC, id ASC
            """
        ),
        {"tenant_id": tenant_id, "run_id": run_id},
    ).mappings().all()
    if not plan_rows:
        return []

    plans: list[dict] = []
    for plan_row in plan_rows:
        plan = dict(plan_row)
        plan["metadata_json"] = _loads_json(plan.get("metadata_json"))
        step_rows = db.execute(
            text(
                """
                SELECT plan_step_id, plan_id, run_id, step_code, step_order, step_title,
                       step_type, tool_name, depends_on_json, status, input_summary,
                       output_summary, linked_step_id, error_message, metadata_json,
                       created_at, updated_at
                FROM agent_run_plan_step
                WHERE tenant_id = :tenant_id AND plan_id = :plan_id
                ORDER BY step_order ASC, id ASC
                """
            ),
            {"tenant_id": tenant_id, "plan_id": plan["plan_id"]},
        ).mappings().all()
        steps: list[dict] = []
        for step_row in step_rows:
            step = dict(step_row)
            # 中文注释：依赖关系用 JSON 数组保存，便于后续 DAG 编排直接扩展。
            step["depends_on_json"] = _loads_json(step.get("depends_on_json"))
            step["metadata_json"] = _loads_json(step.get("metadata_json"))
            steps.append(step)
        plans.append({**plan, "steps": steps})
    return plans


def _load_agent_run_recovery_links(db: Session, tenant_id: str, run_id: str) -> list[dict]:
    """查询当前 Run 参与过的恢复链路，既支持源 Run，也支持恢复后新 Run。"""
    rows = db.execute(
        text(
            """
            SELECT message_id, session_id, run_id, content, metadata_json, created_at
            FROM agent_chat_message
            WHERE tenant_id = :tenant_id
              AND tool_name = 'agent_chat.recovery_event'
              AND (
                run_id = :run_id
                OR JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.recovery_event.source_run_id')) = :run_id
                OR JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.recovery_event.new_run_id')) = :run_id
              )
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """
        ),
        {"tenant_id": tenant_id, "run_id": run_id},
    ).mappings().all()
    links: list[dict] = []
    for row in rows:
        item = dict(row)
        metadata = _loads_json(item.get("metadata_json"))
        item["metadata_json"] = metadata
        item["recovery_event"] = metadata.get("recovery_event") if isinstance(metadata, dict) else {}
        links.append(item)
    return links


def _build_agent_run_timeline(
    *,
    run_data: dict,
    steps: list[dict],
    plans: list[dict],
    rag_traces: list[dict],
    action_runs: list[dict],
    recovery_links: list[dict],
) -> list[dict]:
    """中文注释：Trace Timeline V2 只聚合现有数据，不引入新表，保证旧详情结构继续兼容。"""
    items: list[dict] = []
    run_id = run_data.get("run_id")

    if run_data.get("started_at"):
        items.append(
            {
                "event_type": "run",
                "title": "Run 开始",
                "status": run_data.get("status"),
                "occurred_at": run_data.get("started_at"),
                "finished_at": run_data.get("finished_at"),
                "duration_ms": run_data.get("total_duration_ms") or 0,
                "ref_id": run_id,
                "metadata": {
                    "run_type": run_data.get("run_type"),
                    "graph_name": run_data.get("graph_name"),
                },
            }
        )

    for plan in plans:
        items.append(
            {
                "event_type": "plan",
                "title": plan.get("plan_title") or "执行计划",
                "status": plan.get("status"),
                "occurred_at": plan.get("planned_at") or plan.get("created_at"),
                "finished_at": plan.get("finished_at"),
                "duration_ms": 0,
                "ref_id": plan.get("plan_id"),
                "metadata": {
                    "plan_type": plan.get("plan_type"),
                    "step_count": len(plan.get("steps") or []),
                    "source_intent": plan.get("source_intent"),
                },
            }
        )

    for step in steps:
        items.append(
            {
                "event_type": "step",
                "title": step.get("node_name") or "Agent Step",
                "status": step.get("status"),
                "occurred_at": step.get("started_at") or step.get("created_at"),
                "finished_at": step.get("finished_at"),
                "duration_ms": step.get("duration_ms") or 0,
                "ref_id": step.get("step_id"),
                "metadata": {
                    "node_name": step.get("node_name"),
                    "tool_name": step.get("tool_name"),
                    "error_message": step.get("error_message"),
                },
            }
        )

    for rag_trace in rag_traces:
        items.append(
            {
                "event_type": "rag",
                "title": "RAG 检索",
                "status": "success",
                "occurred_at": rag_trace.get("created_at"),
                "finished_at": rag_trace.get("created_at"),
                "duration_ms": rag_trace.get("total_ms") or 0,
                "ref_id": rag_trace.get("trace_id"),
                "metadata": {
                    "strategy": rag_trace.get("strategy"),
                    "hit_count": rag_trace.get("hit_count"),
                    "top_k": rag_trace.get("top_k"),
                },
            }
        )

    for action_run in action_runs:
        items.append(
            {
                "event_type": "action_run",
                "title": action_run.get("chain_code") or "动作链",
                "status": action_run.get("status"),
                "occurred_at": action_run.get("created_at"),
                "finished_at": action_run.get("finished_at"),
                "duration_ms": 0,
                "ref_id": action_run.get("action_run_id"),
                "metadata": {
                    "approval_id": action_run.get("approval_id"),
                    "current_step_code": action_run.get("current_step_code"),
                    "can_retry": action_run.get("can_retry"),
                },
            }
        )
        for step in action_run.get("steps") or []:
            items.append(
                {
                    "event_type": "action_step",
                    "title": step.get("step_code") or "动作步骤",
                    "status": step.get("status"),
                    "occurred_at": step.get("started_at") or step.get("created_at"),
                    "finished_at": step.get("finished_at"),
                    "duration_ms": 0,
                    "ref_id": step.get("step_run_id"),
                    "metadata": {
                        "tool_name": step.get("tool_name"),
                        "action_run_id": action_run.get("action_run_id"),
                        "retry_count": step.get("retry_count"),
                        "error_message": step.get("error_message"),
                    },
                }
            )

    for link in recovery_links:
        event = link.get("recovery_event") or {}
        recovery_title = event.get("title") or event.get("action") or "恢复事件"
        items.append(
            {
                "event_type": "recovery",
                "title": recovery_title,
                "status": event.get("status") or "opened",
                "occurred_at": link.get("created_at"),
                "finished_at": link.get("created_at"),
                "duration_ms": 0,
                "ref_id": link.get("message_id"),
                "metadata": {
                    "action": event.get("action"),
                    "source_run_id": event.get("source_run_id"),
                    "new_run_id": event.get("new_run_id"),
                    "resume_from_step": event.get("resume_from_step"),
                    "title": recovery_title,
                },
            }
        )

    return sorted(items, key=lambda item: str(item.get("occurred_at") or ""))


def _build_tool_failure_metrics(db: Session, tenant_id: str, limit: int = 1000) -> dict:
    """中文注释：基于 agent_step 聚合工具稳定性，V1 先按最近 N 条 Step 做轻量统计。"""
    safe_limit = max(1, min(int(limit or 1000), 5000))
    rows = db.execute(
        text(
            """
            SELECT step_id, run_id, node_name, tool_name, status, error_message,
                   duration_ms, started_at, finished_at, created_at
            FROM agent_step
            WHERE tenant_id = :tenant_id
              AND tool_name IS NOT NULL
              AND tool_name <> ''
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": safe_limit},
    ).mappings().all()

    metrics_by_tool: dict[str, dict] = {}
    for row in rows:
        tool_name = row["tool_name"]
        item = metrics_by_tool.setdefault(
            tool_name,
            {
                "tool_name": tool_name,
                "total_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "running_count": 0,
                "avg_duration_ms": 0,
                "_duration_sum": 0,
                "_duration_count": 0,
                "latest_failed_step": None,
            },
        )
        item["total_count"] += 1
        status = row["status"]
        if status == "success":
            item["success_count"] += 1
        elif status == "failed":
            item["failed_count"] += 1
            if item["latest_failed_step"] is None:
                item["latest_failed_step"] = {
                    "step_id": row["step_id"],
                    "run_id": row["run_id"],
                    "node_name": row["node_name"],
                    "error_message": row["error_message"],
                    "created_at": row["created_at"],
                }
        elif status == "skipped":
            item["skipped_count"] += 1
        elif status == "running":
            item["running_count"] += 1

        duration_ms = int(row["duration_ms"] or 0)
        item["_duration_sum"] += duration_ms
        item["_duration_count"] += 1

    tools: list[dict] = []
    for item in metrics_by_tool.values():
        duration_count = item.pop("_duration_count")
        duration_sum = item.pop("_duration_sum")
        finished_count = item["success_count"] + item["failed_count"] + item["skipped_count"]
        item["avg_duration_ms"] = round(duration_sum / duration_count, 2) if duration_count else 0
        item["failure_rate"] = round(item["failed_count"] / finished_count, 4) if finished_count else 0
        tools.append(item)

    tools.sort(key=lambda item: (item["failed_count"], item["failure_rate"], item["total_count"]), reverse=True)
    return {
        "sample_size": len(rows),
        "tool_count": len(tools),
        "total_failed_count": sum(item["failed_count"] for item in tools),
        "tools": tools,
    }


def _build_llm_usage_metrics(db: Session, tenant_id: str, limit: int = 1000) -> dict:
    """中文注释：基于 llm_call_log 聚合 LLM token、耗时和成本，先服务 Observability V1。"""
    safe_limit = max(1, min(int(limit or 1000), 5000))
    rows = db.execute(
        text(
            """
            SELECT call_id, user_id, source, provider, model, status, prompt_tokens,
                   completion_tokens, total_tokens, latency_ms, estimated_cost,
                   currency, error_message, created_at
            FROM llm_call_log
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": safe_limit},
    ).mappings().all()

    total_tokens = 0
    total_latency_ms = 0
    failed_count = 0
    total_estimated_cost = 0.0
    latest_failed_call = None
    groups_by_key: dict[tuple[str, str], dict] = {}

    for row in rows:
        token_count = int(row["total_tokens"] or 0)
        latency_ms = int(row["latency_ms"] or 0)
        estimated_cost = float(row["estimated_cost"] or 0)
        total_tokens += token_count
        total_latency_ms += latency_ms
        total_estimated_cost += estimated_cost
        if row["status"] == "failed":
            failed_count += 1
            if latest_failed_call is None:
                latest_failed_call = {
                    "call_id": row["call_id"],
                    "source": row["source"],
                    "model": row["model"],
                    "error_message": row["error_message"],
                    "created_at": row["created_at"],
                }

        group_key = (row["source"], row["model"])
        group = groups_by_key.setdefault(
            group_key,
            {
                "source": row["source"],
                "model": row["model"],
                "provider": row["provider"],
                "call_count": 0,
                "failed_count": 0,
                "total_tokens": 0,
                "avg_latency_ms": 0,
                "estimated_cost": 0.0,
                "_latency_sum": 0,
            },
        )
        group["call_count"] += 1
        group["failed_count"] += 1 if row["status"] == "failed" else 0
        group["total_tokens"] += token_count
        group["_latency_sum"] += latency_ms
        group["estimated_cost"] += estimated_cost

    groups: list[dict] = []
    for group in groups_by_key.values():
        latency_sum = group.pop("_latency_sum")
        group["avg_latency_ms"] = round(latency_sum / group["call_count"], 2) if group["call_count"] else 0
        group["estimated_cost"] = round(group["estimated_cost"], 6)
        groups.append(group)

    groups.sort(key=lambda item: (item["total_tokens"], item["call_count"]), reverse=True)
    return {
        "sample_size": len(rows),
        "call_count": len(rows),
        "failed_count": failed_count,
        "total_tokens": total_tokens,
        "avg_latency_ms": round(total_latency_ms / len(rows), 2) if rows else 0,
        "estimated_cost": round(total_estimated_cost, 6),
        "currency": rows[0]["currency"] if rows else "USD",
        "latest_failed_call": latest_failed_call,
        "groups": groups,
    }


def _percentile_ms(values: list[int], percentile: float) -> float:
    """中文注释：使用线性插值计算百分位，样本少时也能得到稳定可解释的结果。"""
    if not values:
        return 0
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return float(sorted_values[lower_index])
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return round(lower_value + (upper_value - lower_value) * (position - lower_index), 2)


def _latency_distribution(values: list[int]) -> dict:
    """中文注释：统一输出耗时分布字段，前端可以直接渲染 Runtime / LLM 两类指标。"""
    clean_values = [int(value or 0) for value in values if int(value or 0) >= 0]
    return {
        "sample_size": len(clean_values),
        "avg_ms": round(sum(clean_values) / len(clean_values), 2) if clean_values else 0,
        "p50_ms": _percentile_ms(clean_values, 0.5),
        "p95_ms": _percentile_ms(clean_values, 0.95),
        "p99_ms": _percentile_ms(clean_values, 0.99),
        "max_ms": max(clean_values) if clean_values else 0,
    }


def _build_latency_distribution_metrics(db: Session, tenant_id: str, limit: int = 1000) -> dict:
    """中文注释：聚合 Runtime Step 与 LLM 调用耗时分布，用于定位慢节点。"""
    safe_limit = max(1, min(int(limit or 1000), 5000))
    step_rows = db.execute(
        text(
            """
            SELECT step_id, run_id, node_name, tool_name, status, duration_ms, created_at
            FROM agent_step
            WHERE tenant_id = :tenant_id
              AND duration_ms IS NOT NULL
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": safe_limit},
    ).mappings().all()
    llm_rows = db.execute(
        text(
            """
            SELECT call_id, source, model, status, latency_ms, created_at
            FROM llm_call_log
            WHERE tenant_id = :tenant_id
              AND latency_ms IS NOT NULL
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "limit": safe_limit},
    ).mappings().all()

    step_values = [int(row["duration_ms"] or 0) for row in step_rows]
    llm_values = [int(row["latency_ms"] or 0) for row in llm_rows]
    slow_operations: list[dict] = []
    for row in step_rows:
        slow_operations.append(
            {
                "operation_type": "agent_step",
                "ref_id": row["step_id"],
                "run_id": row["run_id"],
                "name": row["tool_name"] or row["node_name"],
                "status": row["status"],
                "duration_ms": int(row["duration_ms"] or 0),
                "created_at": row["created_at"],
            }
        )
    for row in llm_rows:
        slow_operations.append(
            {
                "operation_type": "llm_call",
                "ref_id": row["call_id"],
                "run_id": None,
                "name": f"{row['source']} / {row['model']}",
                "status": row["status"],
                "duration_ms": int(row["latency_ms"] or 0),
                "created_at": row["created_at"],
            }
        )
    slow_operations.sort(key=lambda item: item["duration_ms"], reverse=True)

    return {
        "runtime": _latency_distribution(step_values),
        "llm": _latency_distribution(llm_values),
        "slow_operations": slow_operations[:10],
    }


def _collect_action_approval_ids(run_output: object) -> list[str]:
    """中文注释：优先从 Agent Run 输出里提取审批单，减少详情页回查数据库的次数。"""
    if not isinstance(run_output, dict):
        return []

    approval_ids: list[str] = []
    direct_approval_id = run_output.get("approval_id")
    if isinstance(direct_approval_id, str) and direct_approval_id:
        approval_ids.append(direct_approval_id)

    items = run_output.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            approval_id = item.get("approval_id")
            if isinstance(approval_id, str) and approval_id:
                approval_ids.append(approval_id)

    return list(dict.fromkeys(approval_ids))


def _load_latest_customer_risk_snapshot(db: Session, tenant_id: str, customer_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT risk_snapshot_id, risk_score, risk_level, llm_reason, llm_suggestion, status, created_at
            FROM customer_risk_snapshot
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().first()
    return dict(row) if row else {}


def _load_customer_memory_item(db: Session, tenant_id: str, customer_id: str) -> dict:
    return memory_service.load_customer_memory_map(db, tenant_id, [customer_id]).get(customer_id, {})


def _load_chat_session_or_404(db: Session, current_user: dict, session_id: str) -> dict:
    try:
        return chat_session_service.get_chat_session(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _build_recovery_event_summary(messages: list[dict]) -> dict | None:
    """从统一对话消息中聚合恢复动作事件，供前端和列表页复用。"""
    events: list[dict] = []
    for message in messages:
        metadata = message.get("metadata_json") or {}
        event = metadata.get("recovery_event") if isinstance(metadata, dict) else None
        if isinstance(event, dict):
            events.append(event)
    if not events:
        return None
    return {
        "total": len(events),
        "failed_count": sum(1 for event in events if event.get("status") == "failed"),
        "succeeded_count": sum(1 for event in events if event.get("status") == "succeeded"),
        "running_count": sum(1 for event in events if event.get("status") == "running"),
        "last_event": events[-1],
    }


def _attach_recovery_event_summaries(db: Session, current_user: dict, sessions: list[dict]) -> list[dict]:
    """给会话列表批量补充恢复事件摘要，避免前端进入详情前看不到恢复状态。"""
    session_ids = [item["session_id"] for item in sessions]
    if not session_ids:
        return sessions

    rows = db.execute(
        text(
            """
            SELECT session_id, metadata_json
            FROM agent_chat_message
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND session_id IN :session_ids
              AND tool_name = 'agent_chat.recovery_event'
            ORDER BY created_at ASC, id ASC
            """
        ).bindparams(bindparam("session_ids", expanding=True)),
        {
            "tenant_id": current_user["tenant_id"],
            "user_id": current_user["user_id"],
            "session_ids": session_ids,
        },
    ).mappings().all()

    events_by_session: dict[str, list[dict]] = {session_id: [] for session_id in session_ids}
    for row in rows:
        metadata = _loads_json(row.get("metadata_json"))
        event = metadata.get("recovery_event") if isinstance(metadata, dict) else None
        if isinstance(event, dict):
            events_by_session.setdefault(row["session_id"], []).append(event)

    enriched: list[dict] = []
    for session in sessions:
        events = events_by_session.get(session["session_id"], [])
        summary = None
        if events:
            summary = {
                "total": len(events),
                "failed_count": sum(1 for event in events if event.get("status") == "failed"),
                "succeeded_count": sum(1 for event in events if event.get("status") == "succeeded"),
                "running_count": sum(1 for event in events if event.get("status") == "running"),
                "last_event": events[-1],
            }
        enriched.append({**session, "recovery_event_summary": summary})
    return enriched


def _list_recovery_event_records(db: Session, current_user: dict, session_id: str, limit: int = 100) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT message_id, session_id, content, run_id, metadata_json, created_at
            FROM agent_chat_message
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND session_id = :session_id
              AND tool_name = 'agent_chat.recovery_event'
            ORDER BY created_at ASC, id ASC
            LIMIT :limit
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "user_id": current_user["user_id"],
            "session_id": session_id,
            "limit": max(1, min(limit, 500)),
        },
    ).mappings().all()
    records: list[dict] = []
    for row in rows:
        item = dict(row)
        metadata = _loads_json(item.get("metadata_json"))
        item["metadata_json"] = metadata
        item["recovery_event"] = metadata.get("recovery_event") if isinstance(metadata, dict) else None
        records.append(item)
    return records


def _build_recovery_event_stats(db: Session, current_user: dict, limit: int = 1000) -> dict:
    rows = db.execute(
        text(
            """
            SELECT session_id, content, run_id, metadata_json, created_at
            FROM agent_chat_message
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND tool_name = 'agent_chat.recovery_event'
            ORDER BY created_at ASC, id ASC
            LIMIT :limit
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "user_id": current_user["user_id"],
            "limit": max(1, min(limit, 2000)),
        },
    ).mappings().all()
    counters = {"opened": 0, "running": 0, "succeeded": 0, "failed": 0}
    latest_failed_event = None
    for row in rows:
        metadata = _loads_json(row.get("metadata_json"))
        event = metadata.get("recovery_event") if isinstance(metadata, dict) else None
        if not isinstance(event, dict):
            continue
        status = event.get("status")
        if status in counters:
            counters[status] += 1
        if status == "failed":
            latest_failed_event = {
                "session_id": row["session_id"],
                "content": row["content"],
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "recovery_event": event,
            }

    total = sum(counters.values())
    finished = counters["succeeded"] + counters["failed"]
    success_rate = round(counters["succeeded"] / finished, 4) if finished else 0
    return {
        "total_count": total,
        "opened_count": counters["opened"],
        "running_count": counters["running"],
        "succeeded_count": counters["succeeded"],
        "failed_count": counters["failed"],
        "success_rate": success_rate,
        "latest_failed_event": latest_failed_event,
    }


def _load_latest_data_query_context(messages: list[dict]) -> dict | None:
    """从统一会话中提取最近一次数据查询上下文，支持下一轮继续追问。"""
    for index in range(len(messages) - 1, -1, -1):
        item = messages[index]
        if item.get("role") != "assistant":
            continue
        metadata = item.get("metadata_json") or {}
        if metadata.get("runtime_handler") not in {
            "nl2sql_tool",
            "data.query_sql",
            "data.analyze_business",
            "manager.make_decision",
        }:
            continue

        previous_question = ""
        for previous in reversed(messages[:index]):
            if previous.get("role") == "user":
                previous_question = str(previous.get("content") or "")
                break

        return {
            "question": previous_question,
            "sql": metadata.get("sql"),
            "query_id": metadata.get("query_id"),
            "nl2sql_session_id": metadata.get("nl2sql_session_id"),
            "row_count": metadata.get("row_count"),
        }
    return None


def _load_latest_recommended_actions(messages: list[dict]) -> list[dict]:
    """读取最近一次可执行建议动作，供执行 Agent 转成审批草稿。"""
    for item in reversed(messages):
        if item.get("role") != "assistant":
            continue
        metadata = item.get("metadata_json") or {}
        if metadata.get("runtime_handler") == "manager.make_decision":
            decision = metadata.get("decision") or {}
            actions = decision.get("recommended_actions")
            return actions if isinstance(actions, list) else []
        if metadata.get("runtime_handler") == "opportunity.scan":
            actions = metadata.get("recommended_actions")
            if isinstance(actions, list):
                return actions
            opportunity = metadata.get("opportunity") or {}
            actions = opportunity.get("recommended_actions")
            return actions if isinstance(actions, list) else []
        if metadata.get("runtime_handler") == "followup.plan_strategy":
            actions = metadata.get("recommended_actions")
            if isinstance(actions, list):
                return actions
            strategy = metadata.get("strategy") or {}
            actions = strategy.get("recommended_actions")
            return actions if isinstance(actions, list) else []
    return []


def _load_latest_manager_decision_actions(messages: list[dict]) -> list[dict]:
    """兼容旧测试和调用语义；实际会读取最近一次可执行建议动作。"""
    return _load_latest_recommended_actions(messages)


def _load_latest_opportunity_actions(messages: list[dict]) -> list[dict]:
    for item in reversed(messages):
        if item.get("role") != "assistant":
            continue
        metadata = item.get("metadata_json") or {}
        if metadata.get("runtime_handler") != "opportunity.scan":
            continue
        actions = metadata.get("recommended_actions")
        if isinstance(actions, list):
            return actions
        opportunity = metadata.get("opportunity") or {}
        actions = opportunity.get("recommended_actions")
        return actions if isinstance(actions, list) else []
    return []


def _build_risk_chat_session_payload(
    db: Session,
    current_user: dict,
    customer_id: str,
) -> dict:
    customer = crm_service.load_customer_or_404(db, current_user, customer_id)
    latest_risk = _load_latest_customer_risk_snapshot(db, current_user["tenant_id"], customer_id)
    customer_memory = _load_customer_memory_item(db, current_user["tenant_id"], customer_id)
    conversation_memory = conversation_memory_service.load_conversation_memory(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
    )
    return {
        "session_key": conversation_memory["session_key"],
        "recent_messages": conversation_memory["recent_messages"],
        "history_summary": conversation_memory["history_summary"],
        "memory_window": conversation_memory["memory_window"],
        "updated_at": conversation_memory["updated_at"],
        "customer_brief": {
            "customer_id": customer["customer_id"],
            "customer_name": customer.get("customer_name"),
            "owner_user_id": customer.get("owner_user_id"),
            "owner_user_name": customer.get("owner_user_name"),
            "lifecycle_stage": customer.get("lifecycle_stage"),
            "intent_level": customer.get("intent_level"),
            "last_follow_up_at": customer.get("last_follow_up_at"),
            "next_follow_up_at": customer.get("next_follow_up_at"),
            "last_sentiment": customer.get("last_sentiment"),
        },
        "latest_risk": latest_risk,
        "customer_memory_summary": customer_memory.get("summary_text", ""),
        "customer_memory_updated_at": customer_memory.get("last_compiled_at"),
    }


def _run_risk_agent_chat_reply(db: Session, current_user: dict, customer_id: str, user_message: str) -> dict:
    """复用现有 Risk Agent 对话能力，给统一入口和旧 Risk Chat 保持同一套回复与记忆逻辑。"""
    customer = crm_service.load_customer_or_404(db, current_user, customer_id)
    latest_risk = _load_latest_customer_risk_snapshot(db, current_user["tenant_id"], customer_id)
    customer_memory = _load_customer_memory_item(db, current_user["tenant_id"], customer_id)
    conversation_memory = conversation_memory_service.load_conversation_memory(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
    )

    reply = generate_risk_chat_reply(
        customer=customer,
        latest_risk=latest_risk,
        customer_memory=customer_memory,
        conversation_memory={
            "history_summary": conversation_memory.get("history_summary", ""),
            "recent_messages": [
                *list(conversation_memory.get("recent_messages", [])),
                {
                    "role": "user",
                    "content": user_message,
                    "created_at": "pending",
                },
            ],
        },
        user_message=user_message,
    )
    saved_memory, compacted = conversation_memory_service.append_conversation_messages(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
        messages=[
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ],
    )
    session_items = conversation_memory_service.upsert_conversation_session_index(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id=customer_id,
        customer_name=customer.get("customer_name") or customer_id,
        session_key=saved_memory["session_key"],
        recent_messages=saved_memory["recent_messages"],
        updated_at=saved_memory["updated_at"],
        latest_risk_level=latest_risk.get("risk_level"),
    )

    return {
        "reply": reply,
        "session_key": saved_memory["session_key"],
        "recent_messages": saved_memory["recent_messages"],
        "history_summary": saved_memory["history_summary"],
        "memory_window": saved_memory["memory_window"],
        "updated_at": saved_memory["updated_at"],
        "compacted": compacted,
        "customer_memory_summary": customer_memory.get("summary_text", ""),
        "latest_risk": latest_risk,
        "session_history": session_items,
    }


def _append_failed_runtime_trace_reply(
    db: Session,
    current_user: dict,
    *,
    session_id: str,
    user_message: dict,
    route_result: intent_router.IntentRouteResult,
    resolved_intent: str,
    handler: str,
    exc: Exception,
    tool_route: dict | None = None,
) -> tuple[dict, dict]:
    """工具异常时写入一条失败助手消息，并同步落 Agent Trace。"""
    error_message = str(exc)[:1000] or "工具运行失败"
    recovery_plan = _build_runtime_recovery_plan(handler, resolved_intent, error_message)
    recovery_lines = "\n".join(f"- {item['title']}：{item['description']}" for item in recovery_plan)
    reply = f"工具运行失败，已记录 Trace 供排查。\n\n错误：{error_message}\n\n恢复建议\n{recovery_lines}"
    assistant_message = chat_session_service.append_chat_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="assistant",
        content=reply,
        intent=resolved_intent,
        tool_name=handler,
        metadata_json={
            "runtime_handler": handler,
            "runtime_status": "failed",
            "runtime_error": error_message,
            "tool_route": tool_route or {},
            "recovery_plan": recovery_plan,
        },
    )
    trace_result = chat_runtime_trace_service.record_failed_runtime_trace(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        user_message=user_message,
        assistant_message=assistant_message,
        intent_route=route_result.model_dump(),
        handler=handler,
        error_message=error_message,
        recovery_plan=recovery_plan,
        tool_route=tool_route,
    )
    return assistant_message, {
        "handled": True,
        "handler": handler,
        "status": "failed",
        "reason": "工具运行失败，已写入 Trace",
        "error": error_message,
        "tool_route": tool_route or {},
        "recovery_plan": recovery_plan,
        "reply": reply,
        "run_id": trace_result["run_id"],
        "step_id": trace_result["step_id"],
        "step_ids": trace_result["step_ids"],
        "planner": trace_result["planner"],
        "coordinator": trace_result["coordinator"],
        "plan_id": trace_result["plan_id"],
        "plan_step_id": trace_result["plan_step_id"],
        "plan_step_ids": trace_result["plan_step_ids"],
    }


def _build_runtime_recovery_plan(handler: str, intent: str, error_message: str) -> list[dict]:
    """根据失败工具生成可执行恢复建议，避免用户只看到技术报错。"""
    plan = [
        {
            "action": "inspect_trace",
            "title": "查看 Trace",
            "description": "打开本次 Trace，确认失败节点、输入上下文和错误信息。",
        },
        {
            "action": "retry",
            "title": "重试",
            "description": "如果是临时数据或服务抖动，可在同一会话里重新发送请求。",
        },
    ]
    if intent == intent_router.INTENT_FOLLOW_UP_STRATEGY:
        plan.append(
            {
                "action": "check_customer_context",
                "title": "补齐客户上下文",
                "description": "确认会话已关联客户，并检查客户画像、商机、风险和跟进记录是否完整。",
            }
        )
    if intent == intent_router.INTENT_OPPORTUNITY_ANALYSIS:
        plan.append(
            {
                "action": "narrow_scope",
                "title": "缩小扫描范围",
                "description": "可先限定客户或负责人，降低商机扫描的数据范围。",
            }
        )
    if "permission" in error_message.lower() or "权限" in error_message:
        plan.append(
            {
                "action": "check_permission",
                "title": "检查权限",
                "description": "确认当前账号具备客户读取和对应 Agent 运行权限。",
            }
        )
    plan.append(
        {
            "action": "manual_review",
            "title": "转人工排查",
            "description": f"保留工具名 {handler} 和 Trace Run ID，交给管理员或开发人员定位。",
        }
    )
    return plan


@router.get("/runs")
def list_agent_runs(
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT ar.run_id, ar.user_id, starter.real_name AS user_real_name, ar.run_type, ar.graph_name,
                   ar.status, ar.total_duration_ms, ar.started_at, ar.finished_at
            FROM agent_run ar
            LEFT JOIN sys_user starter
              ON starter.tenant_id = ar.tenant_id
             AND starter.user_id = ar.user_id
            WHERE ar.tenant_id = :tenant_id
            ORDER BY ar.started_at DESC
            LIMIT 100
            """
        ),
        {"tenant_id": current_user["tenant_id"]},
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.get("/tool-metrics/failures")
def get_agent_tool_failure_metrics(
    limit: int = 1000,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    """查询工具失败率、成功数和平均耗时，供 Observability 指标卡使用。"""
    metrics = _build_tool_failure_metrics(db, current_user["tenant_id"], limit=limit)
    return success(metrics, "查询成功", total=metrics["tool_count"])


@router.get("/llm-metrics/usage")
def get_agent_llm_usage_metrics(
    limit: int = 1000,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    """查询 LLM token、模型、耗时和预估成本，供 Observability 指标卡使用。"""
    metrics = _build_llm_usage_metrics(db, current_user["tenant_id"], limit=limit)
    return success(metrics, "查询成功", total=metrics["call_count"])


@router.get("/latency-metrics/distribution")
def get_agent_latency_distribution_metrics(
    limit: int = 1000,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    """查询 Runtime Step 与 LLM 调用耗时分布，供慢节点定位使用。"""
    metrics = _build_latency_distribution_metrics(db, current_user["tenant_id"], limit=limit)
    return success(metrics, "查询成功", total=len(metrics["slow_operations"]))


@router.get("/runs/{run_id}")
def get_agent_run_detail(
    run_id: str,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    """查询单次 Agent Run 的完整审计链路，包括节点、RAG 检索和动作链恢复信息。"""
    run = db.execute(
        text(
            """
            SELECT ar.run_id, ar.user_id, starter.real_name AS user_real_name, ar.run_type, ar.graph_name,
                   ar.input_json, ar.output_json, ar.status, ar.error_message, ar.started_at, ar.finished_at,
                   ar.total_duration_ms, ar.created_at
            FROM agent_run ar
            LEFT JOIN sys_user starter
              ON starter.tenant_id = ar.tenant_id
             AND starter.user_id = ar.user_id
            WHERE ar.tenant_id = :tenant_id AND ar.run_id = :run_id
            LIMIT 1
            """
        ),
        {"tenant_id": current_user["tenant_id"], "run_id": run_id},
    ).mappings().first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent Run 不存在")

    run_data = dict(run)
    run_data["input_json"] = _loads_json(run_data.get("input_json"))
    run_data["output_json"] = _loads_json(run_data.get("output_json"))

    step_rows = db.execute(
        text(
            """
            SELECT step_id, run_id, node_name, tool_name, required_permissions_json,
                   input_json, output_json, status, error_message, started_at, finished_at,
                   duration_ms, created_at
            FROM agent_step
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            ORDER BY started_at ASC, id ASC
            """
        ),
        {"tenant_id": current_user["tenant_id"], "run_id": run_id},
    ).mappings().all()

    steps: list[dict] = []
    trace_ids: list[str] = []
    for row in step_rows:
        step = dict(row)
        step["required_permissions_json"] = _loads_json(step.get("required_permissions_json"))
        step["input_json"] = _loads_json(step.get("input_json"))
        step["output_json"] = _loads_json(step.get("output_json"))
        trace_ids.extend(_collect_trace_ids_from_step(step))
        steps.append(step)

    rag_traces: list[dict] = []
    for trace_id in dict.fromkeys(trace_ids):
        trace_row = db.execute(
            text(
                """
                SELECT trace_id, user_id, original_query, rewritten_query, strategy,
                       rewrite_ms, embed_ms, search_ms, rerank_ms, total_ms, top_k,
                       hit_count, created_at
                FROM rag_retrieval_trace
                WHERE tenant_id = :tenant_id AND trace_id = :trace_id
                LIMIT 1
                """
            ),
            {"tenant_id": current_user["tenant_id"], "trace_id": trace_id},
        ).mappings().first()
        if not trace_row:
            continue
        hit_rows = db.execute(
            text(
                """
                SELECT hit_id, source_collection, source_type, doc_id, section_id,
                       rank_no, dense_score, sparse_score, rrf_score, rerank_score,
                       text_preview, created_at
                FROM rag_retrieval_hit
                WHERE tenant_id = :tenant_id AND trace_id = :trace_id
                ORDER BY rank_no ASC
                """
            ),
            {"tenant_id": current_user["tenant_id"], "trace_id": trace_id},
        ).mappings().all()
        rag_traces.append({**dict(trace_row), "hits": [dict(hit) for hit in hit_rows]})

    approval_ids = _collect_action_approval_ids(run_data.get("output_json"))
    if not approval_ids:
        approval_ids = db.execute(
            text(
                """
                SELECT approval_id
                FROM approval_record
                WHERE tenant_id = :tenant_id AND run_id = :run_id
                ORDER BY created_at DESC
                """
            ),
            {"tenant_id": current_user["tenant_id"], "run_id": run_id},
        ).scalars().all()

    action_runs = _load_action_run_bundles(
        db,
        current_user["tenant_id"],
        [approval_id for approval_id in dict.fromkeys(approval_ids) if approval_id],
    )
    plans = _load_agent_run_plans(db, current_user["tenant_id"], run_id)
    recovery_links = _load_agent_run_recovery_links(db, current_user["tenant_id"], run_id)
    timeline = _build_agent_run_timeline(
        run_data=run_data,
        steps=steps,
        plans=plans,
        rag_traces=rag_traces,
        action_runs=action_runs,
        recovery_links=recovery_links,
    )

    return success(
        {
            "run": run_data,
            "plans": plans,
            "steps": steps,
            "rag_traces": rag_traces,
            "action_runs": action_runs,
            "recovery_links": recovery_links,
            "timeline": timeline,
        },
        "查询成功",
        total=len(steps),
    )


@router.post("/chat/sessions")
def create_agent_chat_session(
    body: AgentChatSessionCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """创建统一 Agent 对话会话；V1 先做入口和持久化，不触发具体 Agent Runtime。"""
    if body.related_customer_id:
        # 中文注释：如果会话挂客户，必须先复用 CRM 权限校验，避免越权创建客户上下文会话。
        crm_service.load_customer_or_404(db, current_user, body.related_customer_id)

    data = chat_session_service.create_chat_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        agent_scope=body.agent_scope,
        intent=body.intent,
        title=body.title,
        related_customer_id=body.related_customer_id,
        context_json=body.context_json,
    )
    return success(data, "统一 Agent 对话会话已创建")


@router.get("/chat/sessions")
def list_agent_chat_sessions(
    agent_scope: str | None = None,
    status: str = "active",
    recovery_status: str | None = None,
    limit: int = 50,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """查询当前用户的统一 Agent 对话会话列表。"""
    if recovery_status and recovery_status not in {"any", "opened", "running", "succeeded", "failed"}:
        raise HTTPException(status_code=400, detail="恢复状态筛选参数无效")
    data = chat_session_service.list_chat_sessions(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        agent_scope=agent_scope,
        status=status,
        recovery_status=recovery_status,
        limit=limit,
    )
    data = _attach_recovery_event_summaries(db, current_user, data)
    return success(data, "查询成功", total=len(data))


@router.get("/chat/recovery-events/stats")
def get_agent_chat_recovery_event_stats(
    limit: int = 1000,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """查询当前用户统一 Agent 对话恢复事件基础统计。"""
    stats = _build_recovery_event_stats(db, current_user, limit=limit)
    return success(stats, "查询成功", total=stats["total_count"])


@router.get("/chat/sessions/{session_id}")
def get_agent_chat_session_detail(
    session_id: str,
    limit: int = 100,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """查询统一 Agent 对话会话详情和消息明细。"""
    session = _load_chat_session_or_404(db, current_user, session_id)
    messages = chat_session_service.list_chat_messages(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        limit=limit,
    )
    return success(
        {
            "session": session,
            "messages": messages,
            "recovery_event_summary": _build_recovery_event_summary(messages),
        },
        "查询成功",
        total=len(messages),
    )


@router.get("/chat/sessions/{session_id}/recovery-events")
def list_agent_chat_recovery_events(
    session_id: str,
    limit: int = 100,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """查询单个统一 Agent 对话会话下的恢复事件历史。"""
    _load_chat_session_or_404(db, current_user, session_id)
    records = _list_recovery_event_records(db, current_user, session_id, limit=limit)
    return success(records, "查询成功", total=len(records))


@router.post("/chat/intent")
def route_agent_chat_intent(
    body: AgentChatIntentRouteRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """识别统一 Agent 对话意图；V1 只返回路由结果，不执行具体工具。"""
    _ = current_user
    result = intent_router.route_intent(body.question)
    return success(result.model_dump(), "意图识别完成")


@router.get("/chat/tools")
def list_agent_chat_tools(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """查询统一对话 Tool Router 当前可选择的工具清单。"""
    specs = list_agent_chat_tool_specs(current_user)
    return success(specs, "查询成功", total=len(specs))


@router.post("/chat/sessions/{session_id}/messages")
def append_agent_chat_user_message(
    session_id: str,
    body: AgentChatMessageCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
    readonly_db: Session = Depends(get_readonly_db),
):
    """统一入口写入用户消息；Agent 回复会在后续 Runtime 接入时由服务层写入。"""
    if body.role != "user":
        raise HTTPException(status_code=400, detail="统一对话入口 V1 仅允许直接写入用户消息")

    current_session = _load_chat_session_or_404(db, current_user, session_id)
    route_result = intent_router.route_intent(body.content)
    resolved_intent = body.intent or route_result.intent
    if (
        not body.intent
        and resolved_intent == intent_router.INTENT_BUSINESS_ANALYSIS
        and current_session.get("agent_scope") == "risk"
        and current_session.get("related_customer_id")
    ):
        # 中文注释：风险工作台里的“为什么风险升高”属于单客户风险对话，不抢到经营分析 Agent。
        resolved_intent = intent_router.INTENT_RISK_ANALYSIS
    existing_messages = chat_session_service.list_chat_messages(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        limit=20,
    )
    data_context_intents = {
        intent_router.INTENT_DATA_QUERY,
        intent_router.INTENT_BUSINESS_ANALYSIS,
        intent_router.INTENT_MANAGER_DECISION,
    }
    data_query_context = _load_latest_data_query_context(existing_messages) if resolved_intent in data_context_intents else None
    tool_route = route_agent_chat_tool(
        intent=resolved_intent,
        agent_scope=current_session.get("agent_scope") or "general",
        current_user=current_user,
        has_related_customer=bool(current_session.get("related_customer_id")),
    ).model_dump()
    message = chat_session_service.append_chat_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="user",
        content=body.content,
        intent=resolved_intent,
        tool_name=body.tool_name,
        run_id=body.run_id,
        trace_id=body.trace_id,
        metadata_json={
            **(body.metadata_json or {}),
            "intent_route": route_result.model_dump(),
        },
    )
    assistant_message = None
    runtime_result = {
        "handled": False,
        "handler": None,
        "tool_route": tool_route,
        "reason": "当前意图暂未接入统一运行时",
    }

    if resolved_intent == intent_router.INTENT_DATA_QUERY:
        nl2sql_result = nl2sql_tool.run_nl2sql_tool(
            db,
            readonly_db,
            current_user,
            question=body.content,
            session_id=(data_query_context or {}).get("nl2sql_session_id"),
            context_payload=data_query_context,
        )
        tool_route = nl2sql_result.get("tool_route") or tool_route
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=nl2sql_result["reply"],
            intent=resolved_intent,
            tool_name="data.query_sql",
            metadata_json={
                "runtime_handler": "data.query_sql",
                "query_id": nl2sql_result["query_id"],
                "nl2sql_session_id": nl2sql_result["nl2sql_session_id"],
                "is_cached": nl2sql_result["is_cached"],
                "row_count": nl2sql_result["row_count"],
                "error": nl2sql_result["error"],
                "sql": nl2sql_result["nl2sql"].get("sql"),
                "followup_context": data_query_context or {},
                "tool_route": tool_route,
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "data.query_sql",
            "tool_route": tool_route,
            "reply": nl2sql_result["reply"],
            "nl2sql": nl2sql_result["nl2sql"],
        }
    elif resolved_intent == intent_router.INTENT_BUSINESS_ANALYSIS:
        analyst_result = data_analyst_tool.run_data_analyst_tool(
            db,
            readonly_db,
            current_user,
            question=body.content,
            session_id=(data_query_context or {}).get("nl2sql_session_id"),
            context_payload=data_query_context,
        )
        tool_route = analyst_result.get("tool_route") or tool_route
        query = analyst_result["analysis_result"].get("query") or {}
        analysis = analyst_result["analysis_result"].get("analysis") or {}
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=analyst_result["reply"],
            intent=resolved_intent,
            tool_name="data.analyze_business",
            metadata_json={
                "runtime_handler": "data.analyze_business",
                "query_id": analyst_result["query_id"],
                "nl2sql_session_id": analyst_result["nl2sql_session_id"],
                "is_cached": analyst_result["is_cached"],
                "row_count": analyst_result["row_count"],
                "error": analyst_result["error"],
                "sql": query.get("sql"),
                "analysis": analysis,
                "followup_context": data_query_context or {},
                "tool_route": tool_route,
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "data.analyze_business",
            "tool_route": tool_route,
            "reply": analyst_result["reply"],
            "analysis": analyst_result["analysis_result"],
        }
    elif resolved_intent == intent_router.INTENT_MANAGER_DECISION:
        manager_result = manager_tool.run_manager_decision_tool(
            db,
            readonly_db,
            current_user,
            question=body.content,
            session_id=(data_query_context or {}).get("nl2sql_session_id"),
            context_payload=data_query_context,
        )
        manager_payload = manager_result["manager_result"]
        decision = manager_payload.get("decision") or {}
        data_analysis = manager_payload.get("data_analysis") or {}
        query = data_analysis.get("query") or {}
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=manager_result["reply"],
            intent=resolved_intent,
            tool_name="manager.make_decision",
            metadata_json={
                "runtime_handler": "manager.make_decision",
                "query_id": manager_result["query_id"],
                "nl2sql_session_id": manager_result["nl2sql_session_id"],
                "row_count": manager_result["row_count"],
                "error": manager_result["error"],
                "sql": query.get("sql"),
                "decision": decision,
                "recommended_action_count": manager_result["recommended_action_count"],
                "followup_context": data_query_context or {},
                "tool_route": tool_route,
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "manager.make_decision",
            "tool_route": tool_route,
            "reply": manager_result["reply"],
            "manager": manager_payload,
        }
    elif resolved_intent == intent_router.INTENT_ACTION_EXECUTION:
        actions = _load_latest_recommended_actions(existing_messages)
        if actions:
            execution_result = execution_tool.run_execution_proposal_tool(
                db,
                current_user,
                actions=actions,
            )
            assistant_message = chat_session_service.append_chat_message(
                db,
                tenant_id=current_user["tenant_id"],
                user_id=current_user["user_id"],
                session_id=session_id,
                role="assistant",
                content=execution_result["reply"],
                intent=resolved_intent,
                tool_name="execution.propose_actions",
                metadata_json={
                    "runtime_handler": "execution.propose_actions",
                    "approval_count": execution_result["approval_count"],
                    "approvals": execution_result["approvals"],
                    "execution": execution_result["execution_result"],
                    "tool_route": tool_route,
                },
            )
            runtime_result = {
                "handled": True,
                "handler": "execution.propose_actions",
                "tool_route": tool_route,
                "reply": execution_result["reply"],
                "execution": execution_result["execution_result"],
            }
        else:
            runtime_result = {
                "handled": False,
                "handler": "execution.propose_actions",
                "tool_route": tool_route,
                "reason": "当前会话没有可提交审批的上一轮建议动作",
            }
    elif resolved_intent == intent_router.INTENT_OPPORTUNITY_ANALYSIS:
        try:
            opportunity_result = opportunity_tool.run_opportunity_scan_tool(
                db,
                current_user,
                question=body.content,
                customer_id=current_session.get("related_customer_id"),
            )
            assistant_message = chat_session_service.append_chat_message(
                db,
                tenant_id=current_user["tenant_id"],
                user_id=current_user["user_id"],
                session_id=session_id,
                role="assistant",
                content=opportunity_result["reply"],
                intent=resolved_intent,
                tool_name="opportunity.scan",
                metadata_json={
                    "runtime_handler": "opportunity.scan",
                    "total": opportunity_result["total"],
                    "quote_timeout_count": opportunity_result["quote_timeout_count"],
                    "heat_change_count": opportunity_result["heat_change_count"],
                    "priority_count": opportunity_result["priority_count"],
                    "recommended_action_count": opportunity_result["recommended_action_count"],
                    "recommended_actions": opportunity_result["recommended_actions"],
                    "opportunity": opportunity_result["opportunity_result"],
                    "error": opportunity_result["error"],
                    "tool_route": tool_route,
                },
            )
            runtime_result = {
                "handled": True,
                "handler": "opportunity.scan",
                "tool_route": tool_route,
                "reply": opportunity_result["reply"],
                "opportunity": opportunity_result["opportunity_result"],
            }
        except Exception as exc:
            assistant_message, runtime_result = _append_failed_runtime_trace_reply(
                db,
                current_user,
                session_id=session_id,
                user_message=message,
                route_result=route_result,
                resolved_intent=resolved_intent,
                handler="opportunity.scan",
                exc=exc,
                tool_route=tool_route,
            )
    elif resolved_intent == intent_router.INTENT_FOLLOW_UP_STRATEGY and current_session.get("related_customer_id"):
        try:
            strategy_result = followup_strategy_tool.run_followup_strategy_tool(
                db,
                current_user,
                customer_id=current_session["related_customer_id"],
                question=body.content,
            )
            tool_route = strategy_result.get("tool_route") or tool_route
            assistant_message = chat_session_service.append_chat_message(
                db,
                tenant_id=current_user["tenant_id"],
                user_id=current_user["user_id"],
                session_id=session_id,
                role="assistant",
                content=strategy_result["reply"],
                intent=resolved_intent,
                tool_name="followup.plan_strategy",
                metadata_json={
                    "runtime_handler": "followup.plan_strategy",
                    "customer_id": strategy_result["customer_id"],
                    "strategy_level": strategy_result["strategy_level"],
                    "recommended_action_count": strategy_result["recommended_action_count"],
                    "recommended_actions": strategy_result["recommended_actions"],
                    "strategy": strategy_result["strategy_result"],
                    "error": strategy_result["error"],
                    "tool_route": tool_route,
                },
            )
            runtime_result = {
                "handled": True,
                "handler": "followup.plan_strategy",
                "tool_route": tool_route,
                "reply": strategy_result["reply"],
                "strategy": strategy_result["strategy_result"],
            }
        except Exception as exc:
            assistant_message, runtime_result = _append_failed_runtime_trace_reply(
                db,
                current_user,
                session_id=session_id,
                user_message=message,
                route_result=route_result,
                resolved_intent=resolved_intent,
                handler="followup.plan_strategy",
                exc=exc,
                tool_route=tool_route,
            )
    elif resolved_intent == intent_router.INTENT_FOLLOW_UP_STRATEGY:
        runtime_result = {
            "handled": False,
            "handler": "followup.plan_strategy",
            "tool_route": tool_route,
            "reason": "跟进策略生成需要会话先关联客户",
        }
    elif resolved_intent == intent_router.INTENT_CUSTOMER_PROFILE and current_session.get("related_customer_id"):
        profile_result = customer_profile_tool.run_customer_profile_tool(
            db,
            current_user,
            customer_id=current_session["related_customer_id"],
        )
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=profile_result["reply"],
            intent=resolved_intent,
            tool_name="profile.generate_customer_memory",
            metadata_json={
                "runtime_handler": "profile.generate_customer_memory",
                "customer_id": profile_result["customer_id"],
                "profile_tags": profile_result["profile_tags"],
                "summary_text": profile_result["summary_text"],
                "tool_route": tool_route,
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "profile.generate_customer_memory",
            "tool_route": tool_route,
            "reply": profile_result["reply"],
            "profile": profile_result["profile_result"],
        }
    elif resolved_intent == intent_router.INTENT_CUSTOMER_PROFILE:
        runtime_result = {
            "handled": False,
            "handler": "profile.generate_customer_memory",
            "tool_route": tool_route,
            "reason": "客户画像生成需要会话先关联客户",
        }
    elif resolved_intent == intent_router.INTENT_RISK_ANALYSIS and current_session.get("related_customer_id"):
        risk_result = _run_risk_agent_chat_reply(
            db,
            current_user,
            current_session["related_customer_id"],
            body.content,
        )
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=risk_result["reply"],
            intent=resolved_intent,
            metadata_json={
                "runtime_handler": "risk_agent",
                "risk_chat": {
                    "session_key": risk_result["session_key"],
                    "compacted": risk_result["compacted"],
                    "latest_risk": risk_result["latest_risk"],
                },
                "tool_route": tool_route,
            },
        )
        runtime_result = {
            "handled": True,
            "handler": "risk_agent",
            "tool_route": tool_route,
            "reply": risk_result["reply"],
            "risk_chat": risk_result,
        }
    elif resolved_intent == intent_router.INTENT_RISK_ANALYSIS:
        runtime_result = {
            "handled": False,
            "handler": "risk_agent",
            "tool_route": tool_route,
            "reason": "风险分析需要会话先关联客户",
        }

    if assistant_message and runtime_result.get("handled") and runtime_result.get("status") != "failed":
        trace_result = chat_runtime_trace_service.record_successful_runtime_trace(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            user_message=message,
            assistant_message=assistant_message,
            intent_route=route_result.model_dump(),
            runtime_result=runtime_result,
        )
        runtime_result = {
            **runtime_result,
            "run_id": trace_result["run_id"],
            "step_id": trace_result["step_id"],
            "step_ids": trace_result["step_ids"],
            "planner": trace_result["planner"],
            "coordinator": trace_result["coordinator"],
            "plan_id": trace_result["plan_id"],
            "plan_step_id": trace_result["plan_step_id"],
            "plan_step_ids": trace_result["plan_step_ids"],
        }

    session = chat_session_service.get_chat_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
    )
    return success(
        {
            "session": session,
            "message": message,
            "assistant_message": assistant_message,
            "intent_route": route_result.model_dump(),
            "runtime": runtime_result,
        },
        "消息已写入统一 Agent 对话",
    )


@router.post("/chat/sessions/{session_id}/recovery-events")
def record_agent_chat_recovery_event(
    session_id: str,
    body: AgentChatRecoveryActionEventRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """记录统一 Agent 对话恢复动作事件；V1 复用 system 消息作为轻量审计流。"""
    _load_chat_session_or_404(db, current_user, session_id)
    title = body.title or body.action
    content = f"恢复动作事件：{title}（{body.status}）"
    if body.error:
        content = f"{content}；错误：{body.error[:200]}"

    event_payload = {
        "action": body.action,
        "title": title,
        "status": body.status,
        "source_run_id": body.source_run_id,
        "new_run_id": body.new_run_id,
        "error": body.error,
    }
    message = chat_session_service.append_chat_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="system",
        content=content,
        intent="recovery_event",
        tool_name="agent_chat.recovery_event",
        run_id=body.new_run_id or body.source_run_id,
        metadata_json={
            "runtime_handler": "agent_chat.recovery_event",
            "recovery_event": event_payload,
            "source": "agent_chat_page",
            **(body.metadata_json or {}),
        },
    )
    return success(message, "恢复动作事件已记录")


def _recover_agent_run_step(
    *,
    run_id: str,
    step_id: str,
    current_user: dict,
    db: Session,
    recovery_action: str,
    recovery_title: str,
    response_key: str,
    event_source: str,
):
    """执行失败步骤恢复；V1 复用安全工具白名单，禁止外发或审批动作自动恢复。"""
    step_row = db.execute(
        text(
            """
            SELECT ast.step_id, ast.run_id, ast.node_name, ast.tool_name, ast.input_json,
                   ast.output_json, ast.status, ast.error_message, ar.user_id
            FROM agent_step ast
            JOIN agent_run ar
              ON ar.tenant_id = ast.tenant_id
             AND ar.run_id = ast.run_id
            WHERE ast.tenant_id = :tenant_id
              AND ast.run_id = :run_id
              AND ast.step_id = :step_id
              AND ar.user_id = :user_id
            LIMIT 1
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "user_id": current_user["user_id"],
            "run_id": run_id,
            "step_id": step_id,
        },
    ).mappings().first()
    if not step_row:
        raise HTTPException(status_code=404, detail="可恢复步骤不存在或无权访问")
    if step_row["status"] != "failed" or step_row["node_name"] != "agent_chat_tool":
        raise HTTPException(status_code=400, detail="仅支持恢复失败的统一对话工具步骤")

    handler = step_row["tool_name"]
    if handler != "followup.plan_strategy":
        raise HTTPException(status_code=400, detail="该工具暂未开放内部恢复，外发或高风险动作不会自动执行")

    input_payload = _loads_json(step_row["input_json"])
    session_id = input_payload.get("session_id")
    question = input_payload.get("question") or ""
    if not session_id or not question:
        raise HTTPException(status_code=400, detail="原步骤缺少可重试的会话或问题上下文")

    session = _load_chat_session_or_404(db, current_user, session_id)
    if not session.get("related_customer_id"):
        raise HTTPException(status_code=400, detail="跟进策略重试需要会话关联客户")
    user_message = chat_session_service.get_chat_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        message_id=input_payload["message_id"],
    )
    route_payload = input_payload.get("intent_route") or {}

    try:
        retry_result = followup_strategy_tool.run_followup_strategy_tool(
            db,
            current_user,
            customer_id=session["related_customer_id"],
            question=question,
        )
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=retry_result["reply"],
            intent=route_payload.get("intent"),
            tool_name="followup.plan_strategy",
            metadata_json={
                "runtime_handler": "followup.plan_strategy",
                "retry_source_run_id": run_id,
                "retry_source_step_id": step_id,
                "resume_source_run_id": run_id,
                "resume_from_step": step_id,
                "strategy_level": retry_result["strategy_level"],
                "recommended_action_count": retry_result["recommended_action_count"],
                "recommended_actions": retry_result["recommended_actions"],
                "strategy": retry_result["strategy_result"],
                "error": retry_result["error"],
            },
        )
        trace_result = chat_runtime_trace_service.record_successful_runtime_trace(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            intent_route=route_payload,
            runtime_result={
                "handled": True,
                "handler": "followup.plan_strategy",
                "reply": retry_result["reply"],
                "retry": {"source_run_id": run_id, "source_step_id": step_id},
                "resume": {"source_run_id": run_id, "resume_from_step": step_id},
                "strategy": retry_result["strategy_result"],
            },
        )
        recovery_status = "succeeded"
        recovery_error = None
    except Exception as exc:
        recovery_status = "failed"
        recovery_error = str(exc)[:1000] or "步骤重试失败"
        recovery_plan = _build_runtime_recovery_plan(handler, route_payload.get("intent") or "unknown", recovery_error)
        assistant_message = chat_session_service.append_chat_message(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            role="assistant",
            content=f"步骤重试失败，已写入 Trace。错误：{recovery_error}",
            intent=route_payload.get("intent"),
            tool_name=handler,
            metadata_json={
                "runtime_handler": handler,
                "runtime_status": "failed",
                "runtime_error": recovery_error,
                "retry_source_run_id": run_id,
                "retry_source_step_id": step_id,
                "resume_source_run_id": run_id,
                "resume_from_step": step_id,
                "recovery_plan": recovery_plan,
            },
        )
        trace_result = chat_runtime_trace_service.record_failed_runtime_trace(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            intent_route=route_payload,
            handler=handler,
            error_message=recovery_error,
            recovery_plan=recovery_plan,
        )

    event_payload = {
        "action": recovery_action,
        "title": recovery_title,
        "status": recovery_status,
        "source_run_id": run_id,
        "new_run_id": trace_result["run_id"],
        "resume_from_step": step_id,
        "error": recovery_error,
    }
    recovery_event = chat_session_service.append_chat_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="system",
        content=f"恢复动作事件：{recovery_title}（{recovery_status}）",
        intent="recovery_event",
        tool_name="agent_chat.recovery_event",
        run_id=trace_result["run_id"],
        metadata_json={
            "runtime_handler": "agent_chat.recovery_event",
            "recovery_event": event_payload,
            "source": event_source,
            "source_step_id": step_id,
            "new_step_id": trace_result["step_id"],
        },
    )
    return success(
        {
            response_key: event_payload,
            "trace": trace_result,
            "assistant_message": assistant_message,
            "recovery_event": recovery_event,
        },
        f"{recovery_title}已完成",
    )


@router.post("/runs/{run_id}/steps/{step_id}/retry")
def retry_agent_run_step(
    run_id: str,
    step_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """重试失败的统一对话内部工具步骤；V1 只允许无外发副作用的策略类工具。"""
    return _recover_agent_run_step(
        run_id=run_id,
        step_id=step_id,
        current_user=current_user,
        db=db,
        recovery_action="step_retry",
        recovery_title="重试失败步骤",
        response_key="retry",
        event_source="agent_step_retry",
    )


@router.post("/runs/{run_id}/steps/{step_id}/resume")
def resume_agent_run_from_step(
    run_id: str,
    step_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """从指定失败步骤局部恢复，生成新的 Run 并保留源 Run / Step 关联。"""
    return _recover_agent_run_step(
        run_id=run_id,
        step_id=step_id,
        current_user=current_user,
        db=db,
        recovery_action="partial_resume",
        recovery_title="从失败步骤继续",
        response_key="resume",
        event_source="agent_partial_resume",
    )


@router.post("/chat/sessions/{session_id}/close")
def close_agent_chat_session(
    session_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """关闭统一 Agent 对话会话，保留消息审计记录。"""
    _load_chat_session_or_404(db, current_user, session_id)
    data = chat_session_service.close_chat_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
    )
    return success(data, "统一 Agent 对话会话已关闭")


@router.get("/risk-chat/customers/{customer_id}/session")
def get_risk_chat_session(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """读取当前用户在当前客户下的 Risk Agent 对话会话和记忆窗口。"""
    data = _build_risk_chat_session_payload(db, current_user, customer_id)
    return success(data, "查询成功")


@router.get("/risk-chat/sessions")
def list_risk_chat_sessions(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """返回当前用户的对话历史索引，供客户工作台左侧会话列表直接展示。"""
    data = conversation_memory_service.list_conversation_sessions(
        current_user["tenant_id"],
        current_user["user_id"],
    )
    return success(data, "查询成功", total=len(data))


@router.post("/risk-chat/customers/{customer_id}/message")
def send_risk_chat_message(
    customer_id: str,
    body: RiskChatMessageRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """发送一条 Risk Agent 对话消息，并把短期记忆压缩为最近 5 轮全量加历史摘要。"""
    return success(_run_risk_agent_chat_reply(db, current_user, customer_id, body.message), "回复成功")


@router.delete("/risk-chat/customers/{customer_id}/session")
def clear_risk_chat_session(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """清空当前用户在该客户下的 Risk Agent 短期会话记忆。"""
    crm_service.load_customer_or_404(db, current_user, customer_id)
    conversation_memory_service.clear_conversation_memory(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id,
    )
    session_items = conversation_memory_service.remove_conversation_session_index(
        current_user["tenant_id"],
        current_user["user_id"],
        customer_id=customer_id,
    )
    return success({"customer_id": customer_id, "session_history": session_items}, "会话记忆已清空")
