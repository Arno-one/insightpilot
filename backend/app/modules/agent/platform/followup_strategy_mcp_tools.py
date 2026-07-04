from __future__ import annotations

from typing import Any

from app.modules.agent import memory_service
from app.modules.agent.followup_strategy_agent import build_followup_strategy
from app.modules.agent.platform.internal_tools import _load_current_user_context, _require_payload_value, _require_permission
from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.crm import service as crm_service


def build_followup_strategy_mcp_tools() -> list[ToolDefinition]:
    """注册跟进策略 Agent V1 工具，生成策略和待审批跟进动作。"""

    def plan_strategy_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        customer_id = str(_require_payload_value(payload, "customer_id"))
        customer_detail = crm_service.load_customer_detail_bundle(context.db, current_user, customer_id)
        memory_map = memory_service.load_customer_memory_map(context.db, context.tenant_id, [customer_id])
        strategy = build_followup_strategy(
            customer_detail,
            customer_memory=memory_map.get(customer_id, {}),
        )
        return {
            **strategy,
            "question": payload.get("question"),
            "trace": {
                "run_id": context.run_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "customer_id": customer_id,
                "memory_hit": customer_id in memory_map,
                "deal_count": len(customer_detail.get("deals") or []),
                "follow_up_count": len(customer_detail.get("follow_ups") or []),
            },
        }

    return [
        ToolDefinition(
            name="followup.plan_strategy",
            description="基于客户画像、商机、风险和历史跟进生成单客户跟进策略，并输出待审批跟进动作。",
            handler=plan_strategy_tool,
        )
    ]
