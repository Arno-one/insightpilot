from __future__ import annotations

from typing import Any

from app.modules.agent.manager_agent import build_manager_decision
from app.modules.agent.platform.data_mcp_tools import build_data_mcp_tools
from app.modules.agent.platform.internal_tools import (
    _load_current_user_context,
    _require_payload_value,
    _require_permission,
    build_shared_internal_tools,
)
from app.modules.agent.platform.tool_registry import InternalToolRegistry, ToolDefinition, ToolExecutionContext


def _safe_execute(registry: InternalToolRegistry, tool_name: str, context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return registry.execute(tool_name, context, payload)["output"]
    except Exception as exc:
        return {"items": [], "total": 0, "error": str(exc)}


def build_manager_mcp_tools() -> list[ToolDefinition]:
    """注册 Manager Agent V1 工具，只生成决策建议，不触发真实执行动作。"""

    def make_decision_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        question = str(_require_payload_value(payload, "question")).strip()
        registry = InternalToolRegistry([*build_data_mcp_tools(), *build_shared_internal_tools()])

        data_analysis = registry.execute(
            "data.analyze_business",
            context,
            {
                "question": question,
                "session_id": payload.get("session_id"),
                "context": payload.get("context"),
                "report_limit": payload.get("report_limit") or 3,
            },
        )["output"]
        customer_search = _safe_execute(
            registry,
            "crm.search_customer",
            context,
            {
                "keyword": payload.get("keyword"),
                "owner_user_id": payload.get("owner_user_id"),
                "limit": int(payload.get("customer_limit") or 3),
            },
        )

        customer_details: list[dict[str, Any]] = []
        for item in list(customer_search.get("items") or [])[:3]:
            customer_id = item.get("customer_id")
            if not customer_id:
                continue
            detail = _safe_execute(registry, "crm.get_customer_detail", context, {"customer_id": customer_id})
            if detail.get("customer"):
                customer_details.append(detail)

        report_context = data_analysis.get("report_context") or {}
        decision = build_manager_decision(
            question,
            data_analysis=data_analysis,
            customer_search=customer_search,
            customer_details=customer_details,
            report_context=report_context,
        )
        return {
            "protocol": "manager.make_decision.v1",
            "question": question,
            "decision": decision,
            "data_analysis": data_analysis,
            "customer_search": customer_search,
            "customer_details": customer_details,
            "trace": {
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "data_query_id": (data_analysis.get("query") or {}).get("query_id"),
                "customer_count": int(customer_search.get("total") or 0),
                "customer_detail_count": len(customer_details),
                "report_count": int(report_context.get("total") or 0),
            },
        }

    return [
        ToolDefinition(
            name="manager.make_decision",
            description="串联 Data Query、Report、CRM、Risk、Approval 和 Task，输出经理视角结论、依据和建议动作。",
            handler=make_decision_tool,
        )
    ]
