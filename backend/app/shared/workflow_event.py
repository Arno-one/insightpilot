import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id


def _json_default(value: Any):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _dump_detail(detail: dict[str, Any] | None) -> str | None:
    if not detail:
        return None
    return json.dumps(detail, ensure_ascii=False, default=_json_default)


def log_workflow_event(
    db: Session,
    *,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    action_type: str,
    operator_user_id: str,
    customer_id: str,
    approval_id: str | None = None,
    task_id: str | None = None,
    risk_snapshot_id: str | None = None,
    note: str | None = None,
    detail: dict[str, Any] | None = None,
    happened_at: datetime | None = None,
):
    """统一记录审批与任务关键动作，方便后续审计、回放和客户详情时间线复用。"""
    db.execute(
        text(
            """
            INSERT INTO approval_task_event (
              tenant_id, event_id, entity_type, entity_id, approval_id, task_id, customer_id,
              risk_snapshot_id, action_type, operator_user_id, note, detail_json, happened_at
            )
            VALUES (
              :tenant_id, :event_id, :entity_type, :entity_id, :approval_id, :task_id, :customer_id,
              :risk_snapshot_id, :action_type, :operator_user_id, :note, :detail_json, :happened_at
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "event_id": new_id("evt"),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "approval_id": approval_id,
            "task_id": task_id,
            "customer_id": customer_id,
            "risk_snapshot_id": risk_snapshot_id,
            "action_type": action_type,
            "operator_user_id": operator_user_id,
            "note": note,
            "detail_json": _dump_detail(detail),
            "happened_at": happened_at or datetime.now(),
        },
    )
