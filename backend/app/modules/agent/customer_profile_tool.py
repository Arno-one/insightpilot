from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_customer_profile_mcp_tools


def _build_reply(result: dict[str, Any]) -> str:
    tags = result.get("profile_tags") or {}
    lines = ["客户画像已生成并写入 Customer Memory。", ""]
    summary_text = result.get("summary_text")
    if summary_text:
        lines.extend(["画像摘要", str(summary_text)])
    if tags:
        lines.append("结构化标签")
        lines.extend(f"- {key}: {value}" for key, value in tags.items())
    return "\n".join(lines)


def run_customer_profile_tool(
    db_rw: Session,
    current_user: dict,
    *,
    customer_id: str,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一 Agent 的客户画像工具封装；生成并回写 Customer Memory。"""
    registry = InternalToolRegistry(build_customer_profile_mcp_tools())
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id="agent_chat_customer_profile",
        db=db_rw,
    )
    result = registry.execute(
        "profile.generate_customer_memory",
        context,
        {"customer_id": customer_id, "runtime_context": runtime_context or {}},
    )["output"]
    return {
        "reply": _build_reply(result),
        "profile_result": result,
        "customer_id": customer_id,
        "profile_tags": result.get("profile_tags") or {},
        "summary_text": result.get("summary_text") or "",
    }
