import json
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.shared.ids import new_id


def _loads_json(value: Any) -> dict[str, Any] | list[Any]:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _dumps_json(value: dict[str, Any] | list[Any]) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _iso_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value in (None, ""):
        return None
    return str(value)


def load_customer_memory_map(db: Session, tenant_id: str, customer_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not customer_ids:
        return {}

    rows = db.execute(
        text(
            """
            SELECT memory_id, customer_id, memory_scope, summary_text, summary_json, source_run_id, last_compiled_at
            FROM customer_memory
            WHERE tenant_id = :tenant_id
              AND memory_scope = 'customer'
              AND customer_id IN :customer_ids
            """
        ).bindparams(bindparam("customer_ids", expanding=True)),
        {"tenant_id": tenant_id, "customer_ids": customer_ids},
    ).mappings().all()

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        item["summary_json"] = _loads_json(item.get("summary_json")) or {}
        result[item["customer_id"]] = item
    return result


def _build_customer_memory_summary_text(summary_json: dict[str, Any]) -> str:
    profile = summary_json.get("profile", {})
    risk_state = summary_json.get("risk_state", {})
    approval_state = summary_json.get("approval_state", {})
    task_state = summary_json.get("task_state", {})
    follow_up_state = summary_json.get("follow_up_state", {})
    report_state = summary_json.get("report_state", {})
    agent_state = summary_json.get("agent_state", {})

    parts: list[str] = []
    customer_name = profile.get("customer_name") or profile.get("customer_id") or "该客户"
    parts.append(
        f"{customer_name} 当前阶段为 {profile.get('lifecycle_stage', 'unknown')}，"
        f"意向等级 {profile.get('intent_level', 'unknown')}，"
        f"最近情绪 {profile.get('last_sentiment', 'unknown')}。"
    )

    if profile.get("competitor_involved"):
        parts.append("客户当前存在竞品介入，需要优先关注异议处理和差异化价值。")

    if risk_state.get("latest_risk_level"):
        parts.append(
            f"最近风险等级 {risk_state.get('latest_risk_level')}，"
            f"风险分 {risk_state.get('latest_risk_score', 'unknown')}。"
        )

    if approval_state.get("pending_count"):
        parts.append(f"当前仍有 {approval_state['pending_count']} 条待审批动作，避免重复创建审批。")
    elif approval_state.get("latest_status"):
        parts.append(f"最近一次审批结果为 {approval_state['latest_status']}。")

    if task_state.get("active_count"):
        parts.append(f"客户当前有 {task_state['active_count']} 条执行中任务，建议先确认存量动作效果。")

    if follow_up_state.get("latest_follow_up_type") or follow_up_state.get("latest_follow_up_at"):
        parts.append(
            f"最近一次跟进方式为 {follow_up_state.get('latest_follow_up_type', 'unknown')}，"
            f"时间 {follow_up_state.get('latest_follow_up_at', 'unknown')}。"
        )

    if report_state.get("latest_report_summary"):
        parts.append(f"最近经营报告摘要：{str(report_state['latest_report_summary'])[:120]}")

    if agent_state.get("latest_review_summary"):
        parts.append(f"最近一次 Agent 复核结论：{agent_state['latest_review_summary']}")

    return "\n".join(part for part in parts if part).strip()


def build_customer_memory_snapshot(
    db: Session,
    *,
    tenant_id: str,
    customer_id: str,
    source_run_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    runtime_context = runtime_context or {}
    customer = db.execute(
        text(
            """
            SELECT customer_id, customer_name, owner_user_id, lifecycle_stage, intent_level, customer_level,
                   competitor_involved, last_sentiment, next_follow_up_at, last_follow_up_at, updated_at
            FROM crm_customer
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().first()
    if not customer:
        return None

    risk_rows = db.execute(
        text(
            """
            SELECT risk_snapshot_id, risk_score, risk_level, llm_reason, llm_suggestion, status, created_at
            FROM customer_risk_snapshot
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 3
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    approval_rows = db.execute(
        text(
            """
            SELECT approval_id, status, review_comment, reviewed_at, created_at
            FROM approval_record
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    task_rows = db.execute(
        text(
            """
            SELECT task_id, title, priority, status, due_at, completed_at, result_note, created_at
            FROM sales_task
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    follow_up_rows = db.execute(
        text(
            """
            SELECT follow_up_id, follow_up_type, sentiment, next_action, next_follow_up_at, occurred_at
            FROM crm_follow_up_record
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id
            ORDER BY occurred_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id},
    ).mappings().all()

    report_rows = db.execute(
        text(
            """
            SELECT report_id, report_type, report_date, summary, created_at
            FROM business_report
            WHERE tenant_id = :tenant_id
              AND CAST(risk_top_json AS CHAR) LIKE :customer_pattern
            ORDER BY report_date DESC, created_at DESC
            LIMIT 3
            """
        ),
        {"tenant_id": tenant_id, "customer_pattern": f"%{customer_id}%"},
    ).mappings().all()

    latest_risk = dict(risk_rows[0]) if risk_rows else {}
    latest_approval = dict(approval_rows[0]) if approval_rows else {}
    latest_task = dict(task_rows[0]) if task_rows else {}
    latest_follow_up = dict(follow_up_rows[0]) if follow_up_rows else {}
    latest_report = dict(report_rows[0]) if report_rows else {}

    pending_approvals = sum(1 for item in approval_rows if item["status"] == "pending")
    active_tasks = sum(1 for item in task_rows if item["status"] in {"pending", "in_progress"})
    high_risk_count = sum(1 for item in risk_rows if item["risk_level"] == "high")
    medium_or_high_risk_count = sum(1 for item in risk_rows if item["risk_level"] in {"medium", "high"})

    summary_json = {
        "profile": {
            "customer_id": customer["customer_id"],
            "customer_name": customer.get("customer_name"),
            "owner_user_id": customer.get("owner_user_id"),
            "lifecycle_stage": customer.get("lifecycle_stage"),
            "intent_level": customer.get("intent_level"),
            "customer_level": customer.get("customer_level"),
            "competitor_involved": bool(customer.get("competitor_involved")),
            "last_sentiment": customer.get("last_sentiment"),
            "next_follow_up_at": _iso_datetime(customer.get("next_follow_up_at")),
            "last_follow_up_at": _iso_datetime(customer.get("last_follow_up_at")),
            "customer_updated_at": _iso_datetime(customer.get("updated_at")),
        },
        "risk_state": {
            "latest_risk_snapshot_id": latest_risk.get("risk_snapshot_id"),
            "latest_risk_level": latest_risk.get("risk_level"),
            "latest_risk_score": latest_risk.get("risk_score"),
            "latest_reason": latest_risk.get("llm_reason"),
            "latest_suggestion": latest_risk.get("llm_suggestion"),
            "recent_high_risk_count": high_risk_count,
            "recent_medium_or_high_risk_count": medium_or_high_risk_count,
            "latest_risk_created_at": _iso_datetime(latest_risk.get("created_at")),
        },
        "approval_state": {
            "total_count": len(approval_rows),
            "pending_count": pending_approvals,
            "latest_approval_id": latest_approval.get("approval_id"),
            "latest_status": latest_approval.get("status"),
            "latest_review_comment": latest_approval.get("review_comment"),
            "latest_reviewed_at": _iso_datetime(latest_approval.get("reviewed_at")),
        },
        "task_state": {
            "total_count": len(task_rows),
            "active_count": active_tasks,
            "latest_task_id": latest_task.get("task_id"),
            "latest_task_title": latest_task.get("title"),
            "latest_task_status": latest_task.get("status"),
            "latest_task_result_note": latest_task.get("result_note"),
            "latest_due_at": _iso_datetime(latest_task.get("due_at")),
        },
        "follow_up_state": {
            "count": len(follow_up_rows),
            "latest_follow_up_id": latest_follow_up.get("follow_up_id"),
            "latest_follow_up_type": latest_follow_up.get("follow_up_type"),
            "latest_sentiment": latest_follow_up.get("sentiment"),
            "latest_next_action": latest_follow_up.get("next_action"),
            "latest_follow_up_at": _iso_datetime(latest_follow_up.get("occurred_at")),
        },
        "report_state": {
            "report_count": len(report_rows),
            "latest_report_id": latest_report.get("report_id"),
            "latest_report_type": latest_report.get("report_type"),
            "latest_report_date": _iso_datetime(latest_report.get("report_date")),
            "latest_report_summary": latest_report.get("summary"),
        },
        "agent_state": {
            "source_run_id": source_run_id,
            "latest_review_summary": runtime_context.get("review", {}).get("summary"),
            "latest_review_note": runtime_context.get("review", {}).get("review_note"),
            "latest_evidence_used": list(runtime_context.get("review", {}).get("evidence_used", [])),
            "latest_tool_names": [
                item.get("tool_name")
                for item in runtime_context.get("tool_executions", [])
                if isinstance(item, dict) and item.get("tool_name")
            ],
            "latest_advice_title": runtime_context.get("advice", {}).get("task_title"),
            "latest_advice_priority": runtime_context.get("advice", {}).get("priority"),
            "latest_created_approval_id": runtime_context.get("created", {}).get("approval_id"),
        },
    }

    summary_text = _build_customer_memory_summary_text(summary_json)
    return {
        "customer_id": customer_id,
        "memory_scope": "customer",
        "summary_text": summary_text,
        "summary_json": summary_json,
        "source_run_id": source_run_id,
        "last_compiled_at": datetime.now(),
    }


def upsert_customer_memory(
    db: Session,
    *,
    tenant_id: str,
    memory_snapshot: dict[str, Any],
) -> dict[str, Any]:
    existing_memory_id = db.execute(
        text(
            """
            SELECT memory_id
            FROM customer_memory
            WHERE tenant_id = :tenant_id
              AND customer_id = :customer_id
              AND memory_scope = :memory_scope
            LIMIT 1
            """
        ),
        {
            "tenant_id": tenant_id,
            "customer_id": memory_snapshot["customer_id"],
            "memory_scope": memory_snapshot["memory_scope"],
        },
    ).scalar_one_or_none()
    memory_id = existing_memory_id or new_id("memo")

    db.execute(
        text(
            """
            INSERT INTO customer_memory (
              tenant_id, memory_id, customer_id, memory_scope, summary_text, summary_json,
              source_run_id, last_compiled_at
            )
            VALUES (
              :tenant_id, :memory_id, :customer_id, :memory_scope, :summary_text, :summary_json,
              :source_run_id, :last_compiled_at
            )
            ON DUPLICATE KEY UPDATE
              summary_text = VALUES(summary_text),
              summary_json = VALUES(summary_json),
              source_run_id = VALUES(source_run_id),
              last_compiled_at = VALUES(last_compiled_at)
            """
        ),
        {
            "tenant_id": tenant_id,
            "memory_id": memory_id,
            "customer_id": memory_snapshot["customer_id"],
            "memory_scope": memory_snapshot["memory_scope"],
            "summary_text": memory_snapshot["summary_text"],
            "summary_json": _dumps_json(memory_snapshot["summary_json"]),
            "source_run_id": memory_snapshot["source_run_id"],
            "last_compiled_at": memory_snapshot["last_compiled_at"],
        },
    )

    return {
        "memory_id": memory_id,
        "customer_id": memory_snapshot["customer_id"],
        "memory_scope": memory_snapshot["memory_scope"],
        "summary_text": memory_snapshot["summary_text"],
        "summary_json": memory_snapshot["summary_json"],
        "source_run_id": memory_snapshot["source_run_id"],
        "last_compiled_at": memory_snapshot["last_compiled_at"].isoformat(),
    }
