from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent import intent_router
from app.modules.agent.platform.data_mcp_tools import build_data_mcp_tools
from app.modules.agent.platform.followup_strategy_mcp_tools import build_followup_strategy_mcp_tools
from app.modules.agent.platform.tool_registry import InternalToolRegistry, ToolExecutionContext


@dataclass(frozen=True, slots=True)
class ToolRoutePolicy:
    """中文注释：描述一个意图到工具的稳定映射，V1 先用确定性规则承接 Planner 输出。"""

    intent: str
    tool_name: str
    required_permissions: tuple[str, ...]
    allowed_scopes: tuple[str, ...] = ("general", "customer", "risk")
    requires_customer: bool = False


@dataclass(frozen=True, slots=True)
class ToolRouteResult:
    """中文注释：Tool Router 的可审计结果，会写入消息 metadata 和 Agent Trace。"""

    router: str
    intent: str
    agent_scope: str
    selected_tool: str | None
    required_permissions: list[str]
    allowed: bool
    reason: str
    matched_policy: str | None
    available_tools: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "router": self.router,
            "intent": self.intent,
            "agent_scope": self.agent_scope,
            "selected_tool": self.selected_tool,
            "required_permissions": self.required_permissions,
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_policy": self.matched_policy,
            "available_tools": self.available_tools,
        }


AGENT_CHAT_ROUTE_POLICIES: tuple[ToolRoutePolicy, ...] = (
    ToolRoutePolicy(
        intent=intent_router.INTENT_DATA_QUERY,
        tool_name="data.query_sql",
        required_permissions=("crm:customer:read:self",),
    ),
    ToolRoutePolicy(
        intent=intent_router.INTENT_BUSINESS_ANALYSIS,
        tool_name="data.analyze_business",
        required_permissions=("crm:customer:read:self",),
    ),
    ToolRoutePolicy(
        intent=intent_router.INTENT_FOLLOW_UP_STRATEGY,
        tool_name="followup.plan_strategy",
        required_permissions=("crm:customer:read:self",),
        allowed_scopes=("customer", "risk"),
        requires_customer=True,
    ),
)


def build_agent_chat_tool_registry() -> InternalToolRegistry:
    """中文注释：统一 Agent Chat 首批可路由工具池，后续版本继续扩展到更多 Agent 工具。"""
    return InternalToolRegistry(
        [
            *build_data_mcp_tools(),
            *build_followup_strategy_mcp_tools(),
        ]
    )


def list_agent_chat_tool_specs(current_user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """查询统一对话可路由工具，附带权限和当前用户可用性。"""
    registry = build_agent_chat_tool_registry()
    permissions = set((current_user or {}).get("permission_codes") or [])
    policies_by_tool = {policy.tool_name: policy for policy in AGENT_CHAT_ROUTE_POLICIES}
    specs: list[dict[str, Any]] = []
    for spec in registry.list_tool_specs():
        policy = policies_by_tool.get(spec["name"])
        required_permissions = list(policy.required_permissions) if policy else []
        specs.append(
            {
                **spec,
                "router": "agent_chat_tool_router_v1",
                "required_permissions": required_permissions,
                "allowed_scopes": list(policy.allowed_scopes) if policy else [],
                "requires_customer": bool(policy.requires_customer) if policy else False,
                "available": not required_permissions or set(required_permissions).issubset(permissions),
            }
        )
    return specs


def _available_tool_names(registry: InternalToolRegistry) -> list[str]:
    return [item["name"] for item in registry.list_tool_specs()]


def _find_policy(intent: str, tool_name: str | None = None) -> ToolRoutePolicy | None:
    for policy in AGENT_CHAT_ROUTE_POLICIES:
        if tool_name and policy.tool_name == tool_name:
            return policy
        if not tool_name and policy.intent == intent:
            return policy
    return None


def route_agent_chat_tool(
    *,
    intent: str,
    agent_scope: str,
    current_user: dict[str, Any],
    has_related_customer: bool = False,
    preferred_tool: str | None = None,
) -> ToolRouteResult:
    """按意图、会话范围和权限选择统一对话工具，保持旧业务路径可兼容。"""
    registry = build_agent_chat_tool_registry()
    available_tools = _available_tool_names(registry)
    policy = _find_policy(intent, preferred_tool)
    if not policy:
        return ToolRouteResult(
            router="agent_chat_tool_router_v1",
            intent=intent,
            agent_scope=agent_scope,
            selected_tool=preferred_tool,
            required_permissions=[],
            allowed=True,
            reason="当前意图暂未接入 Tool Router，继续走旧兼容路径",
            matched_policy=None,
            available_tools=available_tools,
        )

    if not registry.has_tool(policy.tool_name):
        return ToolRouteResult(
            router="agent_chat_tool_router_v1",
            intent=intent,
            agent_scope=agent_scope,
            selected_tool=policy.tool_name,
            required_permissions=list(policy.required_permissions),
            allowed=False,
            reason="路由命中的工具尚未注册",
            matched_policy=policy.intent,
            available_tools=available_tools,
        )

    if agent_scope not in policy.allowed_scopes:
        return ToolRouteResult(
            router="agent_chat_tool_router_v1",
            intent=intent,
            agent_scope=agent_scope,
            selected_tool=policy.tool_name,
            required_permissions=list(policy.required_permissions),
            allowed=False,
            reason="当前会话范围不允许调用该工具",
            matched_policy=policy.intent,
            available_tools=available_tools,
        )

    if policy.requires_customer and not has_related_customer:
        return ToolRouteResult(
            router="agent_chat_tool_router_v1",
            intent=intent,
            agent_scope=agent_scope,
            selected_tool=policy.tool_name,
            required_permissions=list(policy.required_permissions),
            allowed=False,
            reason="该工具需要会话先关联客户",
            matched_policy=policy.intent,
            available_tools=available_tools,
        )

    permissions = set(current_user.get("permission_codes") or [])
    missing_permissions = [item for item in policy.required_permissions if item not in permissions]
    if missing_permissions:
        return ToolRouteResult(
            router="agent_chat_tool_router_v1",
            intent=intent,
            agent_scope=agent_scope,
            selected_tool=policy.tool_name,
            required_permissions=list(policy.required_permissions),
            allowed=False,
            reason=f"缺少工具权限: {', '.join(missing_permissions)}",
            matched_policy=policy.intent,
            available_tools=available_tools,
        )

    return ToolRouteResult(
        router="agent_chat_tool_router_v1",
        intent=intent,
        agent_scope=agent_scope,
        selected_tool=policy.tool_name,
        required_permissions=list(policy.required_permissions),
        allowed=True,
        reason="已按意图、范围和权限命中工具",
        matched_policy=policy.intent,
        available_tools=available_tools,
    )


def execute_agent_chat_tool(
    *,
    db_rw: Session,
    db_readonly: Session | None,
    current_user: dict[str, Any],
    run_id: str,
    intent: str,
    agent_scope: str,
    payload: dict[str, Any],
    has_related_customer: bool = False,
    preferred_tool: str | None = None,
) -> dict[str, Any]:
    """通过 Tool Router 执行统一对话工具，返回路由结果和标准工具输出。"""
    route = route_agent_chat_tool(
        intent=intent,
        agent_scope=agent_scope,
        current_user=current_user,
        has_related_customer=has_related_customer,
        preferred_tool=preferred_tool,
    )
    if not route.allowed or not route.selected_tool:
        raise PermissionError(route.reason)

    registry = build_agent_chat_tool_registry()
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id=run_id,
        db=db_rw,
        readonly_db=db_readonly,
    )
    tool_result = registry.execute(route.selected_tool, context, payload)
    return {
        "route": route.model_dump(),
        "tool": tool_result,
        "output": tool_result["output"],
    }
