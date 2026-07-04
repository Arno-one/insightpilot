from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_execution_mcp_tools


def _build_reply(result: dict[str, Any]) -> str:
    proposal = result.get("proposal") or {}
    approval_count = int(proposal.get("approval_count") or 0)
    if approval_count <= 0:
        return "当前没有可提交审批的执行建议。"
    lines = [f"已生成 {approval_count} 个执行审批草稿，审批通过后才会触发动作链。", "", "审批草稿"]
    for item in list(proposal.get("approvals") or [])[:5]:
        lines.append(f"- {item.get('approval_id')} / {item.get('customer_id')} / {item.get('status')}")
    return "\n".join(lines)


def run_execution_proposal_tool(
    db_rw: Session,
    current_user: dict,
    *,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """统一 Agent 的执行建议工具封装；只生成审批草稿。"""
    registry = InternalToolRegistry(build_execution_mcp_tools())
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id="agent_chat_execution_proposal",
        db=db_rw,
    )
    result = registry.execute("execution.propose_actions", context, {"actions": actions})["output"]
    proposal = result.get("proposal") or {}
    return {
        "reply": _build_reply(result),
        "execution_result": result,
        "approval_count": int(proposal.get("approval_count") or 0),
        "approvals": list(proposal.get("approvals") or []),
    }
