from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.nl2sql.sql_validator import ensure_limit


MAX_ROWS = 1000
MAX_EXECUTION_TIME_MS = 5000


def serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _set_read_timeout(db: Session) -> None:
    """MySQL 支持 max_execution_time；不支持该变量的测试库直接忽略。"""
    try:
        db.execute(text("SET SESSION max_execution_time = :timeout_ms"), {"timeout_ms": MAX_EXECUTION_TIME_MS})
    except Exception:
        db.rollback()


def check_syntax(sql: str, db: Session, *, tenant_id: str) -> tuple[bool, str]:
    try:
        _set_read_timeout(db)
        db.execute(text(f"EXPLAIN {ensure_limit(sql, MAX_ROWS)}"), {"tenant_id": tenant_id})
        return True, ""
    except Exception as exc:
        db.rollback()
        return False, str(exc)


def execute(sql: str, db: Session, *, tenant_id: str, max_rows: int = MAX_ROWS) -> dict[str, Any]:
    _set_read_timeout(db)
    safe_sql = ensure_limit(sql, max_rows)
    result = db.execute(text(safe_sql), {"tenant_id": tenant_id})
    rows = result.mappings().fetchmany(max_rows)
    serialized_rows = [{key: serialize_value(value) for key, value in row.items()} for row in rows]
    columns = list(serialized_rows[0].keys()) if serialized_rows else list(result.keys())
    return {
        "columns": columns,
        "rows": serialized_rows,
        "row_count": len(serialized_rows),
    }
