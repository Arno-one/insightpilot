import json

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.crm.import_service import build_template_csv, import_csv_file
from app.shared.response import success

router = APIRouter()


def _customer_scope_where(current_user: dict, alias: str = "") -> str:
    """统一客户数据可见范围，避免列表页和详情页各自维护一套权限条件。"""
    prefix = f"{alias}." if alias else ""
    if "crm:customer:read:all" in current_user["permission_codes"]:
        return f"{prefix}tenant_id = :tenant_id"
    if "crm:customer:read:team" in current_user["permission_codes"]:
        return f"{prefix}tenant_id = :tenant_id"
    return f"{prefix}tenant_id = :tenant_id AND {prefix}owner_user_id = :user_id"


def _loads_json(value):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {} if value is None else value
    return json.loads(value)


def _serialize_risk_snapshot(row: dict) -> dict:
    item = dict(row)
    item["rule_hits_json"] = _loads_json(item.get("rule_hits_json")) or []
    item["evidence_json"] = _loads_json(item.get("evidence_json")) or {}
    item["suggested_task_json"] = _loads_json(item.get("suggested_task_json")) or {}
    return item


def _serialize_approval(row: dict) -> dict:
    item = dict(row)
    item["proposed_payload_json"] = _loads_json(item.get("proposed_payload_json")) or {}
    return item


def _load_customer_or_404(db: Session, current_user: dict, customer_id: str) -> dict:
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "customer_id": customer_id,
    }
    where_sql = _customer_scope_where(current_user, "c")
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


@router.get("/import/templates/{entity}.csv")
def download_import_template(
    entity: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """下载三类 CRM 数据的最小必需字段模板。"""
    file_name, csv_content = build_template_csv(entity)
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/import/{entity}")
async def import_crm_csv(
    entity: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """统一处理客户、商机、跟进记录三类 CSV 导入。"""
    result = await import_csv_file(entity, file, current_user, db)
    return success(result, "导入完成")


@router.get("/customers")
def list_customers(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """客户列表，V1 先按角色决定数据范围，后续可下沉到策略对象。"""
    params = {"tenant_id": current_user["tenant_id"], "user_id": current_user["user_id"]}
    where_sql = _customer_scope_where(current_user, "c")

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
            ORDER BY c.updated_at DESC
            LIMIT 100
            """
        ),
        params,
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))


@router.get("/customers/{customer_id}")
def get_customer_detail(
    customer_id: str,
    risk_snapshot_id: str | None = None,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """客户详情聚合接口，围绕一个客户把风险、执行和经营引用汇总到同一个入口。"""
    customer = _load_customer_or_404(db, current_user, customer_id)

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
    risk_snapshots = [_serialize_risk_snapshot(row) for row in risk_rows]

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
            risk_snapshots = [_serialize_risk_snapshot(selected_row), *risk_snapshots[:4]]

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
    approvals = [_serialize_approval(row) for row in approval_rows]

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

    return success(
        {
            "customer": customer,
            "selected_risk_snapshot_id": risk_snapshot_id,
            "risk_snapshots": risk_snapshots,
            "deals": list(deal_rows),
            "follow_ups": list(follow_up_rows),
            "approvals": approvals,
            "tasks": list(task_rows),
            "report_refs": list(report_rows),
        },
        "查询成功",
    )
