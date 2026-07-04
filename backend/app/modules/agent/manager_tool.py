from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_manager_mcp_tools


def _join_section(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return [title, *[f"- {item}" for item in items]]


def _build_reply(result: dict[str, Any]) -> str:
    decision = result.get("decision") or {}
    lines = ["经营决策建议已生成。", ""]
    lines.extend(_join_section("结论", list(decision.get("conclusions") or [])))
    lines.extend(_join_section("依据", list(decision.get("evidence") or [])))

    actions = []
    for action in list(decision.get("recommended_actions") or [])[:5]:
        title = action.get("title") or action.get("action_type") or "建议动作"
        priority = action.get("priority") or "medium"
        suffix = "，需审批" if action.get("requires_approval") else ""
        actions.append(f"[{priority}] {title}{suffix}")
    lines.extend(_join_section("建议动作", actions))
    return "\n".join(lines)


def run_manager_decision_tool(
    db_rw: Session,
    db_readonly: Session,
    current_user: dict,
    *,
    question: str,
    session_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一 Agent 的经营决策工具封装；V1 只生成建议，不自动执行。"""
    registry = InternalToolRegistry(build_manager_mcp_tools())
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id="agent_chat_manager_decision",
        db=db_rw,
        readonly_db=db_readonly,
    )
    payload: dict[str, Any] = {"question": question}
    if session_id:
        payload["session_id"] = session_id
    if context_payload:
        payload["context"] = context_payload
    tool_result = registry.execute("manager.make_decision", context, payload)
    result = tool_result["output"]
    decision = result.get("decision") or {}
    data_analysis = result.get("data_analysis") or {}
    query = data_analysis.get("query") or {}
    return {
        "reply": _build_reply(result),
        "manager_result": result,
        "tool_name": "manager.make_decision",
        "query_id": query.get("query_id"),
        "nl2sql_session_id": query.get("session_id"),
        "row_count": int((query.get("result") or {}).get("row_count") or 0),
        "recommended_action_count": len(decision.get("recommended_actions") or []),
        "error": query.get("error"),
    }
