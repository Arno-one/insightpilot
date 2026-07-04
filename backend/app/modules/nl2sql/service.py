import time
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.llm.usage import estimate_llm_cost, extract_token_usage, record_llm_call
from app.modules.nl2sql import dao
from app.modules.nl2sql.prompt_builder import build_messages
from app.modules.nl2sql.schema_context import build_schema_text, get_tables_with_column
from app.modules.nl2sql.sql_executor import check_syntax, execute
from app.modules.nl2sql.sql_formatter import format_sql, normalize_question
from app.modules.nl2sql.sql_validator import ensure_soft_delete_filters, validate_sql


_cache: dict[str, dict[str, Any]] = {}


def create_session(db: Session, current_user: dict, *, title: str | None, data_scope: str, context_json: dict | None) -> dict:
    """创建 NL2SQL 会话，后续 SQL 执行必须复用该会话的数据边界。"""
    return dao.create_session(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        title=title or "数据问答会话",
        data_scope=data_scope,
        context_json=context_json,
    )


def list_sessions(db: Session, current_user: dict, *, status: str = "active", limit: int = 50) -> list[dict]:
    return dao.list_sessions(db, tenant_id=current_user["tenant_id"], user_id=current_user["user_id"], status=status, limit=limit)


def load_session_detail(db: Session, current_user: dict, *, session_id: str, limit: int = 100) -> dict:
    session = dao.get_session(db, tenant_id=current_user["tenant_id"], user_id=current_user["user_id"], session_id=session_id)
    messages = dao.list_messages(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        limit=limit,
    )
    return {"session": session, "messages": messages}


def append_message(
    db: Session,
    current_user: dict,
    *,
    session_id: str,
    role: str,
    content: str,
    query_id: str | None = None,
    metadata_json: dict | None = None,
) -> dict:
    return dao.append_message(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role=role,
        content=content,
        query_id=query_id,
        metadata_json=metadata_json,
    )


def create_query_audit(db: Session, current_user: dict, *, session_id: str, question: str) -> dict:
    """创建查询审计占位，后续生成、校验、执行阶段会持续更新同一条记录。"""
    return dao.create_query_audit(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        question=question,
    )


def generate_sql(
    question: str,
    schema_text: str | None = None,
    *,
    tenant_id: str = "system",
    user_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """使用原生 OpenAI SDK 调 DeepSeek，保持 NL2SQL 与 Agent Runtime 的 LLM 路径隔离。"""
    if not settings.deepseek_api_key:
        return "UNSUPPORTED", 0

    started = time.perf_counter()
    status = "success"
    error_message = None
    client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    try:
        response = client.chat.completions.create(
            model=settings.nl2sql_model,
            max_tokens=500,
            temperature=0,
            messages=build_messages(question, schema_text=schema_text),
        )
        usage = extract_token_usage(response)
        return response.choices[0].message.content or "UNSUPPORTED", int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        status = "failed"
        error_message = str(exc)[:1000]
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        record_llm_call(
            tenant_id=tenant_id,
            user_id=user_id,
            source="nl2sql.generate_sql",
            model=settings.nl2sql_model,
            status=status,
            latency_ms=elapsed_ms,
            estimated_cost=estimate_llm_cost(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            ),
            error_message=error_message,
            metadata_json=metadata_json,
            **usage,
        )


def _empty_result() -> dict[str, Any]:
    return {"columns": [], "rows": [], "row_count": 0}


def _append_error_message(
    db_rw: Session,
    current_user: dict,
    *,
    session_id: str,
    query_id: str,
    question: str,
    sql: str,
    error: str,
    cost_ms: int,
    metadata_json: dict[str, Any],
) -> dict:
    return dao.append_message(
        db_rw,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session_id,
        role="assistant",
        content=error,
        query_id=query_id,
        question=question,
        generated_sql=sql,
        result_json=_empty_result(),
        cost_ms=cost_ms,
        is_cached=False,
        metadata_json=metadata_json,
    )


def query(db_rw: Session, db_readonly: Session, current_user: dict, *, question: str, session_id: str | None = None) -> dict:
    """NL2SQL 核心 pipeline：缓存 -> LLM -> 格式化 -> 安全校验 -> EXPLAIN -> 执行 -> 持久化。"""
    started = time.perf_counter()
    session = (
        dao.get_session(db_rw, tenant_id=current_user["tenant_id"], user_id=current_user["user_id"], session_id=session_id)
        if session_id
        else create_session(
            db_rw,
            current_user,
            title=question[:30],
            data_scope="self",
            context_json={"source": "nl2sql_query"},
        )
    )
    audit = dao.create_query_audit(
        db_rw,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session["session_id"],
        question=question,
    )

    cache_key = f"{current_user['tenant_id']}:{current_user['user_id']}:{normalize_question(question)}"
    cached = _cache.get(cache_key)
    if cached:
        audit = dao.update_query_audit(
            db_rw,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            query_id=audit["query_id"],
            generated_sql=cached["sql"],
            normalized_sql=cached["sql"],
            status="executed",
            validator_result_json={"valid": True, "cached": True},
            execution_summary_json=cached["result"],
            row_count=cached["result"]["row_count"],
            elapsed_ms=0,
        )
        message = dao.append_message(
            db_rw,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            session_id=session["session_id"],
            role="assistant",
            content=cached["summary"],
            query_id=audit["query_id"],
            question=question,
            generated_sql=cached["sql"],
            result_json=cached["result"],
            cost_ms=0,
            is_cached=True,
            metadata_json={"cache_key": cache_key, "audit": {"status": audit["status"]}},
        )
        return {
            "session_id": session["session_id"],
            "query_id": audit["query_id"],
            "sql": cached["sql"],
            "result": cached["result"],
            "message": message,
            "is_cached": True,
            "cost_ms": 0,
        }

    schema_text = build_schema_text()
    try:
        raw_sql, llm_cost_ms = generate_sql(
            question,
            schema_text=schema_text,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            metadata_json={"session_id": session["session_id"], "query_id": audit["query_id"]},
        )
    except TypeError as exc:
        if "unexpected keyword argument" not in str(exc):
            raise
        # 中文注释：兼容旧测试替身或外部扩展仍使用 V1 的 generate_sql(question, schema_text) 签名。
        raw_sql, llm_cost_ms = generate_sql(question, schema_text=schema_text)
    sql = format_sql(raw_sql)
    valid, error = validate_sql(sql)
    if valid:
        sql = ensure_soft_delete_filters(sql, get_tables_with_column("is_deleted"))
        valid, error = validate_sql(sql)

    if not valid:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        audit = dao.update_query_audit(
            db_rw,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            query_id=audit["query_id"],
            generated_sql=raw_sql,
            normalized_sql=sql,
            status="failed",
            validator_result_json={"valid": False, "error": error},
            error_message=error,
            elapsed_ms=elapsed_ms,
        )
        message = _append_error_message(
            db_rw,
            current_user,
            session_id=session["session_id"],
            query_id=audit["query_id"],
            question=question,
            sql=sql,
            error=error,
            cost_ms=llm_cost_ms,
            metadata_json={"validator": {"valid": False, "error": error}},
        )
        return {
            "session_id": session["session_id"],
            "query_id": audit["query_id"],
            "sql": sql,
            "result": _empty_result(),
            "message": message,
            "is_cached": False,
            "error": error,
            "cost_ms": llm_cost_ms,
        }

    syntax_ok, syntax_error = check_syntax(sql, db_readonly, tenant_id=current_user["tenant_id"])
    if not syntax_ok:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        audit = dao.update_query_audit(
            db_rw,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            query_id=audit["query_id"],
            generated_sql=raw_sql,
            normalized_sql=sql,
            status="failed",
            validator_result_json={"valid": True},
            error_message=syntax_error,
            elapsed_ms=elapsed_ms,
        )
        message = _append_error_message(
            db_rw,
            current_user,
            session_id=session["session_id"],
            query_id=audit["query_id"],
            question=question,
            sql=sql,
            error=syntax_error,
            cost_ms=llm_cost_ms,
            metadata_json={"syntax": {"valid": False, "error": syntax_error}},
        )
        return {
            "session_id": session["session_id"],
            "query_id": audit["query_id"],
            "sql": sql,
            "result": _empty_result(),
            "message": message,
            "is_cached": False,
            "error": syntax_error,
            "cost_ms": llm_cost_ms,
        }

    result = execute(sql, db_readonly, tenant_id=current_user["tenant_id"])
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    summary = f"查询完成，返回 {result['row_count']} 行数据。"
    audit = dao.update_query_audit(
        db_rw,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        query_id=audit["query_id"],
        generated_sql=raw_sql,
        normalized_sql=sql,
        status="executed",
        validator_result_json={"valid": True},
        execution_summary_json=result,
        row_count=result["row_count"],
        elapsed_ms=elapsed_ms,
    )
    message = dao.append_message(
        db_rw,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        session_id=session["session_id"],
        role="assistant",
        content=summary,
        query_id=audit["query_id"],
        question=question,
        generated_sql=sql,
        result_json=result,
        cost_ms=llm_cost_ms,
        is_cached=False,
        metadata_json={"validator": {"valid": True}, "audit": {"status": audit["status"]}},
    )
    _cache[cache_key] = {"sql": sql, "result": result, "summary": summary}
    return {
        "session_id": session["session_id"],
        "query_id": audit["query_id"],
        "sql": sql,
        "result": result,
        "message": message,
        "is_cached": False,
        "cost_ms": llm_cost_ms,
    }
