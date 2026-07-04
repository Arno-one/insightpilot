from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_data_mcp_tools


def _join_section(title: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return [title, *[f"- {item}" for item in items]]


def _build_reply(result: dict[str, Any]) -> str:
    query = result.get("query") or {}
    analysis = result.get("analysis") or {}
    if query.get("error"):
        return f"这次没能完成经营分析：{query['error']}"

    lines = [
        f"经营分析完成，基于 {analysis.get('row_count', 0)} 行数据生成解释。",
        "",
        "结论",
        analysis.get("summary") or "已完成经营分析。",
    ]
    lines.extend(_join_section("趋势识别", list(analysis.get("trend_insights") or [])))
    lines.extend(_join_section("异常识别", list(analysis.get("anomaly_insights") or [])))
    lines.extend(_join_section("指标解释", list(analysis.get("metric_explanations") or [])))
    lines.extend(_join_section("TopN 归因摘要", list(analysis.get("topn_attribution") or [])))
    return "\n".join(lines)


def run_data_analyst_tool(
    db_rw: Session,
    db_readonly: Session,
    current_user: dict,
    *,
    question: str,
    session_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一 Agent 的经营分析工具封装；实际执行走标准 data.analyze_business Tool。"""
    registry = InternalToolRegistry(build_data_mcp_tools())
    context = ToolExecutionContext(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        run_id="agent_chat_data_analyst",
        db=db_rw,
        readonly_db=db_readonly,
    )
    payload: dict[str, Any] = {"question": question}
    if session_id:
        payload["session_id"] = session_id
    if context_payload:
        payload["context"] = context_payload
    tool_result = registry.execute("data.analyze_business", context, payload)
    result = tool_result["output"]
    query = result.get("query") or {}
    reply = _build_reply(result)
    return {
        "reply": reply,
        "analysis_result": result,
        "tool_name": "data.analyze_business",
        "query_id": query.get("query_id"),
        "nl2sql_session_id": query.get("session_id"),
        "is_cached": bool(query.get("is_cached")),
        "row_count": int((query.get("result") or {}).get("row_count") or 0),
        "error": query.get("error"),
    }
