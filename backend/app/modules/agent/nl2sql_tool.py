from typing import Any

from sqlalchemy.orm import Session

from app.modules.agent import intent_router
from app.modules.agent.platform import execute_agent_chat_tool


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text if len(text) <= 80 else f"{text[:77]}..."


def _build_reply(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"这次没能生成可执行的数据查询：{result['error']}"

    query_result = result.get("result") or {}
    columns = list(query_result.get("columns") or [])
    rows = list(query_result.get("rows") or [])
    row_count = int(query_result.get("row_count") or 0)
    if not columns:
        return "查询完成，但没有返回可展示的字段。"

    preview_rows = rows[:5]
    lines = [f"查询完成，返回 {row_count} 行数据。", "", " | ".join(columns)]
    lines.append(" | ".join(["---"] * len(columns)))
    for row in preview_rows:
        lines.append(" | ".join(_format_cell(row.get(column)) for column in columns))
    if row_count > len(preview_rows):
        lines.append(f"... 仅展示前 {len(preview_rows)} 行")
    return "\n".join(lines)


def run_nl2sql_tool(
    db_rw: Session,
    db_readonly: Session,
    current_user: dict,
    *,
    question: str,
    session_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """统一 Agent 的 NL2SQL 工具封装；实际执行走标准 data.query_sql Tool。"""
    payload: dict[str, Any] = {"question": question}
    if session_id:
        payload["session_id"] = session_id
    if context_payload:
        payload["context"] = context_payload
    routed_result = execute_agent_chat_tool(
        db_rw=db_rw,
        db_readonly=db_readonly,
        current_user=current_user,
        run_id="agent_chat_data_query",
        intent=intent_router.INTENT_DATA_QUERY,
        agent_scope="general",
        payload=payload,
        preferred_tool="data.query_sql",
    )
    result = routed_result["output"]
    reply = _build_reply(result)
    return {
        "reply": reply,
        "nl2sql": result,
        "tool_name": "data.query_sql",
        "tool_route": routed_result["route"],
        "query_id": result.get("query_id"),
        "nl2sql_session_id": result.get("session_id"),
        "is_cached": bool(result.get("is_cached")),
        "row_count": int((result.get("result") or {}).get("row_count") or 0),
        "error": result.get("error"),
    }
