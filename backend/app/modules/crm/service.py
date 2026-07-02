import json

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


def customer_scope_where(current_user: dict, alias: str = "") -> str:
    """统一客户数据可见范围，避免列表页、详情页和内部工具各自维护权限条件。"""
    prefix = f"{alias}." if alias else ""
    permission_codes = current_user.get("permission_codes", [])
    if "crm:customer:read:all" in permission_codes:
        return f"{prefix}tenant_id = :tenant_id"
    if "crm:customer:read:team" in permission_codes:
        return f"{prefix}tenant_id = :tenant_id"
    return f"{prefix}tenant_id = :tenant_id AND {prefix}owner_user_id = :user_id"


def loads_json(value):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {} if value is None else value
    return json.loads(value)


def serialize_risk_snapshot(row: dict) -> dict:
    item = dict(row)
    item["rule_hits_json"] = loads_json(item.get("rule_hits_json")) or []
    item["evidence_json"] = loads_json(item.get("evidence_json")) or {}
    item["suggested_task_json"] = loads_json(item.get("suggested_task_json")) or {}
    return item


def serialize_approval(row: dict) -> dict:
    item = dict(row)
    item["proposed_payload_json"] = loads_json(item.get("proposed_payload_json")) or {}
    return item


def serialize_workflow_event(row: dict) -> dict:
    item = dict(row)
    item["detail_json"] = loads_json(item.get("detail_json")) or {}
    return item


def load_customer_or_404(db: Session, current_user: dict, customer_id: str) -> dict:
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "customer_id": customer_id,
    }
    where_sql = customer_scope_where(current_user, "c")
    row = db.execute(
        text(
            f"""
            SELECT c.customer_id, c.customer_name, c.owner_user_id, owner.real_name AS owner_user_name,
                   c.industry, c.region, c.source, c.lifecycle_stage, c.intent_level, c.customer_level,
                   c.company_size, c.budget_min, c.budget_max, c.expected_purchase_at,
                   c.decision_maker_status, c.competitor_involved, c.next_follow_up_at, c.last_follow_up_at,
                   c.last_sentiment, c.lost_reason, c.remark, c.created_at, c.updated_at
            FROM crm_customer c
            LEFT JOIN sys_user owner
              ON owner.tenant_id = c.tenant_id
             AND owner.user_id = c.owner_user_id
            WHERE {where_sql}
              AND c.customer_id = :customer_id
            LIMIT 1
            """
        ),
        params,
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="客户不存在或无权查看")
    return dict(row)


def search_customers(
    db: Session,
    current_user: dict,
    *,
    keyword: str | None = None,
    owner_user_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "owner_user_id": owner_user_id,
        "limit": max(1, min(limit, 100)),
    }
    filters: list[str] = []
    if keyword:
        params["keyword"] = f"%{keyword}%"
        filters.append(
            "AND (c.customer_id LIKE :keyword OR c.customer_name LIKE :keyword OR owner.real_name LIKE :keyword)"
        )
    if owner_user_id:
        filters.append("AND c.owner_user_id = :owner_user_id")

    where_sql = customer_scope_where(current_user, "c")
    rows = db.execute(
        text(
            f"""
            SELECT c.customer_id, c.customer_name, c.owner_user_id, owner.real_name AS owner_user_name,
                   c.lifecycle_stage, c.intent_level, c.customer_level, c.competitor_involved,
                   c.last_follow_up_at, c.next_follow_up_at
            FROM crm_customer c
            LEFT JOIN sys_user owner
              ON owner.tenant_id = c.tenant_id
             AND owner.user_id = c.owner_user_id
            WHERE {where_sql}
              {' '.join(filters)}
            ORDER BY c.updated_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def load_customer_detail_bundle(
    db: Session,
    current_user: dict,
    customer_id: str,
    *,
    risk_snapshot_id: str | None = None,
) -> dict:
    """围绕一个客户聚合风险、审批、任务和报告引用，供 API 与内部工具共用。"""
    customer = load_customer_or_404(db, current_user, customer_id)

    risk_rows = db.execute(
        text(
            """
            SELECT rs.risk_snapshot_id, rs.customer_id, rs.deal_id, rs.owner_user_id, owner.real_name AS owner_user_name,
                   rs.risk_score, rs.risk_level, rs.rule_hits_json, rs.evidence_json,
                   rs.llm_reason, rs.llm_suggestion, rs.suggested_task_json, rs.status, rs.created_at
            FROM customer_risk_snapshot rs
            LEFT JOIN sys_user owner
              ON owner.tenant_id = rs.tenant_id
             AND owner.user_id = rs.owner_user_id
            WHERE rs.tenant_id = :tenant_id
              AND rs.customer_id = :customer_id
            ORDER BY rs.created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": current_user["tenant_id"], "customer_id": customer_id},
    ).mappings().all()
    risk_snapshots = [serialize_risk_snapshot(row) for row in risk_rows]

    if risk_snapshot_id and all(item["risk_snapshot_id"] != risk_snapshot_id for item in risk_snapshots):
        selected_row = db.execute(
            text(
                """
                SELECT rs.risk_snapshot_id, rs.customer_id, rs.deal_id, rs.owner_user_id, owner.real_name AS owner_user_name,
                       rs.risk_score, rs.risk_level, rs.rule_hits_json, rs.evidence_json,
                       rs.llm_reason, rs.llm_suggestion, rs.suggested_task_json, rs.status, rs.created_at
                FROM customer_risk_snapshot rs
                LEFT JOIN sys_user owner
                  ON owner.tenant_id = rs.tenant_id
                 AND owner.user_id = rs.owner_user_id
                WHERE rs.tenant_id = :tenant_id
                  AND rs.customer_id = :customer_id
                  AND rs.risk_snapshot_id = :risk_snapshot_id
                LIMIT 1
                """
            ),
            {
                "tenant_id": current_user["tenant_id"],
                "customer_id": customer_id,
                "risk_snapshot_id": risk_snapshot_id,
            },
        ).mappings().first()
        if selected_row:
            risk_snapshots = [serialize_risk_snapshot(selected_row), *risk_snapshots[:4]]

    deal_rows = db.execute(
        text(
            """
            SELECT d.deal_id, d.owner_user_id, owner.real_name AS owner_user_name, d.deal_name, d.stage,
                   d.amount, d.quote_amount, d.quoted_at, d.expected_close_at, d.closed_at, d.close_result, d.updated_at
            FROM crm_deal d
            LEFT JOIN sys_user owner
              ON owner.tenant_id = d.tenant_id
             AND owner.user_id = d.owner_user_id
            WHERE d.tenant_id = :tenant_id
              AND d.customer_id = :customer_id
            ORDER BY d.updated_at DESC
            LIMIT 3
            """
        ),
        {"tenant_id": current_user["tenant_id"], "customer_id": customer_id},
    ).mappings().all()

    follow_up_rows = db.execute(
        text(
            """
            SELECT fr.follow_up_id, fr.deal_id, fr.owner_user_id, owner.real_name AS owner_user_name,
                   fr.follow_up_type, fr.content, fr.sentiment, fr.customer_feedback,
                   fr.next_action, fr.next_follow_up_at, fr.occurred_at
            FROM crm_follow_up_record fr
            LEFT JOIN sys_user owner
              ON owner.tenant_id = fr.tenant_id
             AND owner.user_id = fr.owner_user_id
            WHERE fr.tenant_id = :tenant_id
              AND fr.customer_id = :customer_id
            ORDER BY fr.occurred_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": current_user["tenant_id"], "customer_id": customer_id},
    ).mappings().all()

    approval_rows = db.execute(
        text(
            """
            SELECT ar.approval_id, ar.approval_type, ar.risk_snapshot_id, ar.status,
                   ar.requested_by_user_id, requester.real_name AS requested_by_user_name,
                   ar.reviewer_user_id, reviewer.real_name AS reviewer_user_name,
                   ar.review_comment, ar.created_at, ar.reviewed_at, ar.proposed_payload_json
            FROM approval_record ar
            LEFT JOIN sys_user requester
              ON requester.tenant_id = ar.tenant_id
             AND requester.user_id = ar.requested_by_user_id
            LEFT JOIN sys_user reviewer
              ON reviewer.tenant_id = ar.tenant_id
             AND reviewer.user_id = ar.reviewer_user_id
            WHERE ar.tenant_id = :tenant_id
              AND ar.customer_id = :customer_id
            ORDER BY ar.created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": current_user["tenant_id"], "customer_id": customer_id},
    ).mappings().all()
    approvals = [serialize_approval(row) for row in approval_rows]

    task_rows = db.execute(
        text(
            """
            SELECT t.task_id, t.approval_id, t.deal_id, t.assignee_user_id, assignee.real_name AS assignee_user_name,
                   t.task_type, t.title, t.description, t.recommended_script, t.priority,
                   t.status, t.due_at, t.completed_at, t.result_note, t.created_at
            FROM sales_task t
            LEFT JOIN sys_user assignee
              ON assignee.tenant_id = t.tenant_id
             AND assignee.user_id = t.assignee_user_id
            WHERE t.tenant_id = :tenant_id
              AND t.customer_id = :customer_id
            ORDER BY t.created_at DESC
            LIMIT 5
            """
        ),
        {"tenant_id": current_user["tenant_id"], "customer_id": customer_id},
    ).mappings().all()
    tasks = [dict(row) for row in task_rows]

    event_rows = db.execute(
        text(
            """
            SELECT e.event_id, e.entity_type, e.entity_id, e.approval_id, e.task_id, e.customer_id,
                   e.risk_snapshot_id, e.action_type, e.operator_user_id, operator.real_name AS operator_user_name,
                   e.note, e.detail_json, e.happened_at
            FROM approval_task_event e
            LEFT JOIN sys_user operator
              ON operator.tenant_id = e.tenant_id
             AND operator.user_id = e.operator_user_id
            WHERE e.tenant_id = :tenant_id
              AND e.customer_id = :customer_id
            ORDER BY e.happened_at ASC, e.id ASC
            LIMIT 100
            """
        ),
        {"tenant_id": current_user["tenant_id"], "customer_id": customer_id},
    ).mappings().all()
    workflow_events = [serialize_workflow_event(row) for row in event_rows]
    approval_events: dict[str, list[dict]] = {}
    task_events: dict[str, list[dict]] = {}
    for item in workflow_events:
        if item.get("approval_id"):
            approval_events.setdefault(item["approval_id"], []).append(item)
        if item.get("task_id"):
            task_events.setdefault(item["task_id"], []).append(item)

    for item in approvals:
        item["events"] = approval_events.get(item["approval_id"], [])
    for item in tasks:
        item["events"] = task_events.get(item["task_id"], [])

    report_rows = db.execute(
        text(
            """
            SELECT br.report_id, br.report_type, br.report_date, br.summary, br.suggestions,
                   br.created_by_user_id, creator.real_name AS created_by_user_name, br.created_at
            FROM business_report br
            LEFT JOIN sys_user creator
              ON creator.tenant_id = br.tenant_id
             AND creator.user_id = br.created_by_user_id
            WHERE br.tenant_id = :tenant_id
              AND CAST(br.risk_top_json AS CHAR) LIKE :customer_pattern
            ORDER BY br.report_date DESC, br.created_at DESC
            LIMIT 3
            """
        ),
        {
            "tenant_id": current_user["tenant_id"],
            "customer_pattern": f"%{customer_id}%",
        },
    ).mappings().all()

    return {
        "customer": customer,
        "selected_risk_snapshot_id": risk_snapshot_id,
        "risk_snapshots": risk_snapshots,
        "deals": [dict(row) for row in deal_rows],
        "follow_ups": [dict(row) for row in follow_up_rows],
        "approvals": approvals,
        "tasks": tasks,
        "report_refs": [dict(row) for row in report_rows],
    }
