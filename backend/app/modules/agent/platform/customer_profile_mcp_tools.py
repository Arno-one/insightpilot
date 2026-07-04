from __future__ import annotations

from typing import Any

from app.modules.agent import memory_service
from app.modules.agent.platform.internal_tools import _load_current_user_context, _require_payload_value, _require_permission
from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.crm import service as crm_service


def build_customer_profile_mcp_tools() -> list[ToolDefinition]:
    """注册客户画像 Agent V1 工具，把 CRM 聚合信息写回 Customer Memory。"""

    def generate_customer_memory_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        customer_id = str(_require_payload_value(payload, "customer_id"))
        # 中文注释：生成画像前先复用 CRM 权限校验，避免越权写入客户记忆。
        crm_service.load_customer_or_404(context.db, current_user, customer_id)
        snapshot = memory_service.build_customer_memory_snapshot(
            context.db,
            tenant_id=context.tenant_id,
            customer_id=customer_id,
            source_run_id=context.run_id,
            runtime_context=payload.get("runtime_context") if isinstance(payload.get("runtime_context"), dict) else {},
        )
        if not snapshot:
            raise ValueError("客户不存在，无法生成画像")
        memory = memory_service.upsert_customer_memory(
            context.db,
            tenant_id=context.tenant_id,
            memory_snapshot=snapshot,
        )
        return {
            "protocol": "profile.generate_customer_memory.v1",
            "customer_id": customer_id,
            "memory": memory,
            "profile_tags": memory.get("summary_json", {}).get("profile_tags") or {},
            "summary_text": memory.get("summary_text") or "",
        }

    return [
        ToolDefinition(
            name="profile.generate_customer_memory",
            description="基于 CRM、跟进、商机、风险、审批、任务和报告记录生成标准化客户画像，并回写 Customer Memory。",
            handler=generate_customer_memory_tool,
        )
    ]
