from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.approval.service import create_approval_draft
from app.modules.crm.service import load_customer_detail_bundle, search_customers
from app.modules.report.service import enqueue_report_generation, query_reports


def _load_current_user_context(context: ToolExecutionContext) -> dict:
    user = context.db.execute(
        text(
            """
            SELECT tenant_id, user_id, username, real_name, status, is_deleted
            FROM sys_user
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"tenant_id": context.tenant_id, "user_id": context.user_id},
    ).mappings().first()
    if not user or user["status"] != 1 or user["is_deleted"] != 0:
        raise ValueError("工具执行用户不存在或已失效")

    permission_codes = context.db.execute(
        text(
            """
            SELECT DISTINCT p.permission_code
            FROM sys_user_role ur
            JOIN sys_role_permission rp ON rp.tenant_id = ur.tenant_id AND rp.role_id = ur.role_id
            JOIN sys_permission p ON p.permission_id = rp.permission_id
            WHERE ur.tenant_id = :tenant_id
              AND ur.user_id = :user_id
              AND p.status = 1
            """
        ),
        {"tenant_id": context.tenant_id, "user_id": context.user_id},
    ).scalars().all()

    return {
        "tenant_id": user["tenant_id"],
        "user_id": user["user_id"],
        "username": user["username"],
        "real_name": user["real_name"],
        "permission_codes": sorted(permission_codes),
    }


def _require_permission(current_user: dict, permission_code: str) -> None:
    if permission_code not in current_user.get("permission_codes", []):
        raise PermissionError(f"内部工具缺少权限: {permission_code}")


def _require_payload_value(payload: dict, key: str):
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"内部工具缺少必要字段: {key}")
    return value


def _payload_customer(payload: dict) -> dict:
    customer = payload.get("customer")
    return customer if isinstance(customer, dict) else {}


def _parse_report_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def build_shared_internal_tools() -> list[ToolDefinition]:
    """注册第二批通用内部工具，为后续 MCP / Planner / Multi-Agent 铺底。"""

    def crm_search_tool(context: ToolExecutionContext, payload: dict) -> dict:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        items = search_customers(
            context.db,
            current_user,
            keyword=payload.get("keyword"),
            owner_user_id=payload.get("owner_user_id"),
            limit=int(payload.get("limit", 20)),
        )
        return {
            "items": items,
            "total": len(items),
            "keyword": payload.get("keyword"),
            "owner_user_id": payload.get("owner_user_id"),
        }

    def crm_detail_tool(context: ToolExecutionContext, payload: dict) -> dict:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        customer = _payload_customer(payload)
        customer_id = payload.get("customer_id") or customer.get("customer_id")
        if not customer_id:
            raise ValueError("内部工具缺少必要字段: customer_id")
        return load_customer_detail_bundle(
            context.db,
            current_user,
            customer_id,
            risk_snapshot_id=payload.get("risk_snapshot_id"),
        )

    def report_query_tool(context: ToolExecutionContext, payload: dict) -> dict:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "report:read:team")
        customer = _payload_customer(payload)
        items = query_reports(
            context.db,
            current_user,
            customer_id=payload.get("customer_id") or customer.get("customer_id"),
            owner_user_id=payload.get("owner_user_id") or customer.get("owner_user_id"),
            report_type=payload.get("report_type"),
            date_from=payload.get("date_from"),
            date_to=payload.get("date_to"),
            limit=int(payload.get("limit", 20)),
        )
        return {
            "items": items,
            "total": len(items),
        }

    def report_generate_tool(context: ToolExecutionContext, payload: dict) -> dict:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "agent:run:business_report")
        report_type = str(payload.get("report_type") or "daily")
        report_date = _parse_report_date(payload.get("report_date"))
        job = enqueue_report_generation(current_user, report_type, report_date)
        return {
            "job_id": job.id,
            "report_type": report_type,
            "report_date": report_date.isoformat() if report_date else None,
        }

    def approval_create_draft_tool(context: ToolExecutionContext, payload: dict) -> dict:
        customer_id = _require_payload_value(payload, "customer_id")
        proposed_payload = payload.get("proposed_payload")
        if not isinstance(proposed_payload, dict):
            raise ValueError("内部工具缺少必要字段: proposed_payload")
        return create_approval_draft(
            context.db,
            tenant_id=context.tenant_id,
            customer_id=customer_id,
            proposed_payload=proposed_payload,
            requested_by_user_id=context.user_id,
            approval_type=str(payload.get("approval_type") or "agent_task_draft"),
            run_id=payload.get("run_id") or context.run_id,
            risk_snapshot_id=payload.get("risk_snapshot_id"),
            operator_user_id=context.user_id,
            note=str(payload.get("note") or "AI 建议已进入人工审批队列"),
        )

    return [
        ToolDefinition(
            name="crm.search_customer",
            description="按关键词或负责人搜索客户，用于 Planner 判断客户全貌和下一步动作。",
            handler=crm_search_tool,
        ),
        ToolDefinition(
            name="crm.get_customer_detail",
            description="拉取单个客户的聚合详情，包含风险、审批、任务和报告引用。",
            handler=crm_detail_tool,
        ),
        ToolDefinition(
            name="report.query",
            description="查询历史经营报告，用于复用过往总结、风险趋势和负责人表现。",
            handler=report_query_tool,
        ),
        ToolDefinition(
            name="report.generate",
            description="异步生成日报、周报或月报任务，给后续经营 Agent 触发真实报告产出。",
            handler=report_generate_tool,
        ),
        ToolDefinition(
            name="approval.create_draft",
            description="创建人工审批草稿，先进入审批队列，再由人工决定是否正式落地。",
            handler=approval_create_draft_tool,
        ),
    ]
