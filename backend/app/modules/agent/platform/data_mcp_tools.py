from __future__ import annotations

from typing import Any

from app.core.database import ReadonlySessionLocal
from app.modules.agent.platform.internal_tools import _load_current_user_context, _require_payload_value, _require_permission
from app.modules.agent.platform.tool_registry import ToolDefinition, ToolExecutionContext
from app.modules.nl2sql import service as nl2sql_service


def _build_trace_summary(context: ToolExecutionContext, question: str, result: dict[str, Any]) -> dict[str, Any]:
    query_result = result.get("result") or {}
    return {
        "run_id": context.run_id,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "question": question,
        "query_id": result.get("query_id"),
        "nl2sql_session_id": result.get("session_id"),
        "status": "failed" if result.get("error") else "executed",
        "row_count": int(query_result.get("row_count") or 0),
        "is_cached": bool(result.get("is_cached")),
        "cost_ms": int(result.get("cost_ms") or 0),
        "error": result.get("error"),
    }


def _normalize_query_output(context: ToolExecutionContext, question: str, result: dict[str, Any]) -> dict[str, Any]:
    query_result = result.get("result") or {"columns": [], "rows": [], "row_count": 0}
    trace_summary = _build_trace_summary(context, question, result)
    return {
        "protocol": "data.query_sql.v1",
        "question": question,
        "query_id": result.get("query_id"),
        "session_id": result.get("session_id"),
        "sql": result.get("sql") or "",
        "result": query_result,
        "row_count": trace_summary["row_count"],
        "is_cached": trace_summary["is_cached"],
        "error": result.get("error"),
        "cost_ms": trace_summary["cost_ms"],
        "trace": trace_summary,
    }


def build_data_mcp_tools() -> list[ToolDefinition]:
    """注册 Data MCP V1 工具，先把 NL2SQL 暴露为平台标准数据查询能力。"""

    def query_sql_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        question = str(_require_payload_value(payload, "question")).strip()
        session_id = payload.get("session_id")

        if context.readonly_db is not None:
            result = nl2sql_service.query(context.db, context.readonly_db, current_user, question=question, session_id=session_id)
            return _normalize_query_output(context, question, result)

        # 中文注释：后台 Tool/MCP 调用若没有显式只读连接，就临时打开 NL2SQL 专用只读连接。
        with ReadonlySessionLocal() as readonly_db:
            result = nl2sql_service.query(context.db, readonly_db, current_user, question=question, session_id=session_id)
            return _normalize_query_output(context, question, result)

    return [
        ToolDefinition(
            name="data.query_sql",
            description="通过 NL2SQL 生成并执行只读 SQL，返回结构化结果、SQL、缓存状态和查询审计摘要。",
            handler=query_sql_tool,
        )
    ]
