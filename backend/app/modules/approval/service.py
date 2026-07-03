import json
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from app.shared.ids import new_id
from app.shared.workflow_event import log_workflow_event


def create_approval_draft(
    db: Session,
    *,
    tenant_id: str,
    customer_id: str,
    proposed_payload: dict,
    requested_by_user_id: str,
    approval_type: str = "agent_task_draft",
    run_id: str | None = None,
    risk_snapshot_id: str | None = None,
    operator_user_id: str | None = None,
    note: str = "AI 建议已进入人工审批队列",
) -> dict:
    """统一创建审批草稿，给风险链路和后续通用 Tool Calling 共用。"""
    approval_id = new_id("appr")
    db.execute(
        text(
            """
            INSERT INTO approval_record (
              tenant_id, approval_id, approval_type, run_id, risk_snapshot_id, customer_id,
              proposed_payload_json, status, requested_by_user_id
            )
            VALUES (
              :tenant_id, :approval_id, :approval_type, :run_id, :risk_snapshot_id, :customer_id,
              :proposed_payload_json, 'pending', :requested_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "approval_id": approval_id,
            "approval_type": approval_type,
            "run_id": run_id,
            "risk_snapshot_id": risk_snapshot_id,
            "customer_id": customer_id,
            "proposed_payload_json": json.dumps(proposed_payload, ensure_ascii=False),
            "requested_by_user_id": requested_by_user_id,
        },
    )
    log_workflow_event(
        db,
        tenant_id=tenant_id,
        entity_type="approval",
        entity_id=approval_id,
        approval_id=approval_id,
        customer_id=customer_id,
        risk_snapshot_id=risk_snapshot_id,
        action_type="approval_created",
        operator_user_id=operator_user_id or requested_by_user_id,
        note=note,
        detail={
            "approval_type": approval_type,
            "title": proposed_payload.get("title"),
            "priority": proposed_payload.get("priority"),
            "assignee_user_id": proposed_payload.get("assignee_user_id"),
        },
    )
    return {
        "approval_id": approval_id,
        "approval_type": approval_type,
        "customer_id": customer_id,
        "risk_snapshot_id": risk_snapshot_id,
        "run_id": run_id,
        "status": "pending",
        "requested_by_user_id": requested_by_user_id,
        "proposed_payload_json": proposed_payload,
    }


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
    return json.dumps(value, ensure_ascii=False)


def _build_agent_run_approval_summary(db: Session, tenant_id: str, run_id: str) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT approval_id, status, reviewed_at
            FROM approval_record
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            """
        ),
        {"tenant_id": tenant_id, "run_id": run_id},
    ).mappings().all()

    approval_ids = [row["approval_id"] for row in rows]
    task_count = 0
    if approval_ids:
        task_count = db.execute(
            text(
                """
                SELECT COUNT(1)
                FROM sales_task
                WHERE tenant_id = :tenant_id
                  AND approval_id IN :approval_ids
                """
            ).bindparams(bindparam("approval_ids", expanding=True)),
            {"tenant_id": tenant_id, "approval_ids": approval_ids},
        ).scalar_one()
    pending_count = sum(1 for row in rows if row["status"] == "pending")
    approved_count = sum(1 for row in rows if row["status"] == "approved")
    rejected_count = sum(1 for row in rows if row["status"] == "rejected")
    reviewed_times = [row["reviewed_at"] for row in rows if row["reviewed_at"]]

    return {
        "total_count": len(rows),
        "pending_count": pending_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "processed_count": approved_count + rejected_count,
        "converted_task_count": task_count,
        "all_reviewed": len(rows) > 0 and pending_count == 0,
        "latest_reviewed_at": max(reviewed_times).isoformat() if reviewed_times else None,
    }


def sync_agent_run_after_approval_review(
    db: Session,
    *,
    tenant_id: str,
    approval: dict[str, Any],
    reviewed_status: str,
    reviewed_at: datetime,
    review_comment: str | None,
    reviewer_user_id: str,
    reviewer_user_name: str | None,
    task_id: str | None = None,
    tool_calling_records: list[dict[str, Any]] | None = None,
) -> None:
    """把人工审批结果回写到 Agent Run，补齐 Agent Trace 的人工闭环。"""
    run_id = approval.get("run_id")
    if not run_id:
        return

    run_row = db.execute(
        text(
            """
            SELECT output_json
            FROM agent_run
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "run_id": run_id},
    ).mappings().first()
    if not run_row:
        return

    output = _loads_json(run_row["output_json"])
    if not isinstance(output, dict):
        output = {}

    items = output.get("items")
    if not isinstance(items, list):
        items = []

    human_review = {
        "status": reviewed_status,
        "reviewed_at": reviewed_at.isoformat(),
        "review_comment": review_comment,
        "reviewer_user_id": reviewer_user_id,
        "reviewer_user_name": reviewer_user_name,
        "task_id": task_id,
        "tool_calling_records": list(tool_calling_records or []),
    }

    matched = False
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("approval_id") != approval["approval_id"]:
            continue
        existed_review = item.get("human_review")
        items[index] = {
            **item,
            "approval_status": reviewed_status,
            "reviewed_at": reviewed_at.isoformat(),
            "review_comment": review_comment,
            "reviewer_user_id": reviewer_user_id,
            "reviewer_user_name": reviewer_user_name,
            "task_id": task_id or item.get("task_id"),
            "human_review": {
                **(existed_review if isinstance(existed_review, dict) else {}),
                **human_review,
            },
        }
        matched = True
        break

    if not matched:
        items.append(
            {
                "approval_id": approval["approval_id"],
                "customer_id": approval.get("customer_id"),
                "risk_snapshot_id": approval.get("risk_snapshot_id"),
                "approval_status": reviewed_status,
                "reviewed_at": reviewed_at.isoformat(),
                "review_comment": review_comment,
                "reviewer_user_id": reviewer_user_id,
                "reviewer_user_name": reviewer_user_name,
                "task_id": task_id,
                "human_review": human_review,
            }
        )

    output["items"] = items
    output["approval_count"] = output.get("approval_count") or len(items)
    output["risk_count"] = output.get("risk_count") or len(items)

    summary = _build_agent_run_approval_summary(db, tenant_id, run_id)
    output["approval_summary"] = summary

    run_status = "awaiting_approval" if summary["pending_count"] > 0 else "success"
    db.execute(
        text(
            """
            UPDATE agent_run
            SET output_json = :output_json,
                status = :status
            WHERE tenant_id = :tenant_id AND run_id = :run_id
            """
        ),
        {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "output_json": _dumps_json(output),
            "status": run_status,
        },
    )
