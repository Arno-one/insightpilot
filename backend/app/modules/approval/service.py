import json

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
