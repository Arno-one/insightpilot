from typing import Any

from sqlalchemy.orm import Session

from app.modules.nl2sql import service as nl2sql_service


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
) -> dict[str, Any]:
    """统一 Agent 的 NL2SQL 工具封装；核心生成和执行仍由 NL2SQL service 独立完成。"""
    result = nl2sql_service.query(db_rw, db_readonly, current_user, question=question)
    reply = _build_reply(result)
    return {
        "reply": reply,
        "nl2sql": result,
        "tool_name": "nl2sql_tool",
        "query_id": result.get("query_id"),
        "nl2sql_session_id": result.get("session_id"),
        "is_cached": bool(result.get("is_cached")),
        "row_count": int((result.get("result") or {}).get("row_count") or 0),
        "error": result.get("error"),
    }
