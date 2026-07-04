from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.modules.agent.opportunity_agent import analyze_opportunities
from app.modules.agent.platform.internal_tools import _load_current_user_context, _require_permission
from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.crm import service as crm_service


def _load_opportunity_rows(context: ToolExecutionContext, current_user: dict, payload: dict[str, Any]) -> list[dict[str, Any]]:
    params = {
        "tenant_id": current_user["tenant_id"],
        "user_id": current_user["user_id"],
        "customer_id": payload.get("customer_id"),
        "owner_user_id": payload.get("owner_user_id"),
        "limit": max(1, min(int(payload.get("limit") or 50), 100)),
    }
    filters: list[str] = ["AND d.close_result = 'open'"]
    if payload.get("customer_id"):
        filters.append("AND d.customer_id = :customer_id")
    if payload.get("owner_user_id"):
        filters.append("AND d.owner_user_id = :owner_user_id")

    where_sql = crm_service.customer_scope_where(current_user, "c")
    rows = context.db.execute(
        text(
            f"""
            SELECT d.deal_id, d.customer_id, c.customer_name, d.owner_user_id,
                   owner.real_name AS owner_user_name, d.deal_name, d.stage, d.amount,
                   d.quote_amount, d.quoted_at, d.expected_close_at, d.close_result,
                   d.updated_at, c.intent_level, c.competitor_involved,
                   COALESCE(last_follow.latest_follow_up_at, c.last_follow_up_at) AS last_follow_up_at
            FROM crm_deal d
            JOIN crm_customer c
              ON c.tenant_id = d.tenant_id
             AND c.customer_id = d.customer_id
            LEFT JOIN sys_user owner
              ON owner.tenant_id = d.tenant_id
             AND owner.user_id = d.owner_user_id
            LEFT JOIN (
                SELECT tenant_id, deal_id, MAX(occurred_at) AS latest_follow_up_at
                FROM crm_follow_up_record
                WHERE tenant_id = :tenant_id
                GROUP BY tenant_id, deal_id
            ) last_follow
              ON last_follow.tenant_id = d.tenant_id
             AND last_follow.deal_id = d.deal_id
            WHERE {where_sql}
              {' '.join(filters)}
            ORDER BY d.quoted_at IS NULL ASC, d.quoted_at ASC, d.updated_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def build_opportunity_mcp_tools() -> list[ToolDefinition]:
    """注册 AI 商机分析 Agent V1 工具，只输出建议和信号，不自动执行销售动作。"""

    def scan_opportunity_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        rows = _load_opportunity_rows(context, current_user, payload)
        analysis = analyze_opportunities(
            rows,
            quote_timeout_days=int(payload.get("quote_timeout_days") or 7),
        )
        return {
            **analysis,
            "question": payload.get("question"),
            "scope": {
                "customer_id": payload.get("customer_id"),
                "owner_user_id": payload.get("owner_user_id"),
                "limit": max(1, min(int(payload.get("limit") or 50), 100)),
            },
            "execution_policy": {
                "auto_execute": False,
                "requires_human_approval": True,
                "reason": "商机跟进建议只进入人工判断，不自动触发报价、任务或通知。",
            },
            "trace": {
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "row_count": len(rows),
            },
        }

    return [
        ToolDefinition(
            name="opportunity.scan",
            description="扫描开放商机，识别报价超时、热度变化、成交概率变化和跟进建议。",
            handler=scan_opportunity_tool,
        )
    ]
