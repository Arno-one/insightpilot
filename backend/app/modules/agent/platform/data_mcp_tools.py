from __future__ import annotations

from typing import Any

from app.core.database import ReadonlySessionLocal
from app.modules.agent.data_analyst import analyze_query_result
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


def _build_contextual_question(question: str, context_payload: Any) -> str:
    """把上一轮数据查询上下文压进当前问题，支持“继续追问/缩小过滤条件”的 V1 能力。"""
    if not isinstance(context_payload, dict):
        return question

    previous_sql = str(context_payload.get("sql") or "").strip()
    previous_question = str(context_payload.get("question") or "").strip()
    if not previous_sql and not previous_question:
        return question

    sections = ["【上一轮数据查询上下文】"]
    if previous_question:
        sections.append(f"上一轮问题：{previous_question}")
    if previous_sql:
        sections.append(f"上一轮SQL：{previous_sql}")
    sections.append("【当前追问】")
    sections.append(question)
    return "\n".join(sections)


def build_data_mcp_tools() -> list[ToolDefinition]:
    """注册 Data MCP 工具，把问数和经营分析统一挂到平台数据能力下。"""

    def query_sql_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        current_user = _load_current_user_context(context)
        _require_permission(current_user, "crm:customer:read:self")
        question = str(_require_payload_value(payload, "question")).strip()
        session_id = payload.get("session_id")
        followup_context = payload.get("context")
        effective_question = _build_contextual_question(question, followup_context)

        if context.readonly_db is not None:
            result = nl2sql_service.query(
                context.db,
                context.readonly_db,
                current_user,
                question=effective_question,
                session_id=session_id,
            )
            output = _normalize_query_output(context, question, result)
            output["followup_context"] = followup_context if isinstance(followup_context, dict) else {}
            return output

        # 中文注释：后台 Tool/MCP 调用若没有显式只读连接，就临时打开 NL2SQL 专用只读连接。
        with ReadonlySessionLocal() as readonly_db:
            result = nl2sql_service.query(
                context.db,
                readonly_db,
                current_user,
                question=effective_question,
                session_id=session_id,
            )
            output = _normalize_query_output(context, question, result)
            output["followup_context"] = followup_context if isinstance(followup_context, dict) else {}
            return output

    def analyze_business_tool(context: ToolExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
        # 中文注释：经营分析 V1 不新开数据通道，先复用 data.query_sql 的只读、安全和审计链路。
        question = str(_require_payload_value(payload, "question")).strip()
        query_output = query_sql_tool(context, payload)
        analysis = analyze_query_result(question, query_output)
        trace = {
            **(query_output.get("trace") or {}),
            "analysis_protocol": analysis["protocol"],
            "analysis_status": "generated" if not query_output.get("error") else "skipped",
        }
        return {
            "protocol": "data.analyze_business.v1",
            "question": question,
            "query": query_output,
            "analysis": analysis,
            "trace": trace,
        }

    return [
        ToolDefinition(
            name="data.query_sql",
            description="通过 NL2SQL 生成并执行只读 SQL，返回结构化结果、SQL、缓存状态和查询审计摘要。",
            handler=query_sql_tool,
        ),
        ToolDefinition(
            name="data.analyze_business",
            description="复用 data.query_sql 查询经营数据，并生成趋势、异常、指标解释和 TopN 归因摘要。",
            handler=analyze_business_tool,
        ),
    ]
