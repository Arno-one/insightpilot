import re

from app.modules.nl2sql.sql_formatter import format_sql


FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "CALL",
    "EXEC",
    "SLEEP",
    "INTO OUTFILE",
    "LOAD_FILE",
]

CLAUSE_KEYWORDS = {
    "WHERE",
    "LEFT",
    "RIGHT",
    "INNER",
    "FULL",
    "JOIN",
    "ON",
    "GROUP",
    "ORDER",
    "HAVING",
    "LIMIT",
    "UNION",
}


def strip_comments(sql: str) -> str:
    """移除注释后再做关键字检查，避免危险语句藏在注释边界里。"""
    clean = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    clean = re.sub(r"--[^\n]*", "", clean)
    return clean


def keyword_present(sql_upper: str, keyword: str) -> bool:
    if " " in keyword:
        return keyword in sql_upper
    return bool(re.search(r"\b" + re.escape(keyword) + r"\b", sql_upper))


def validate_sql(sql: str) -> tuple[bool, str]:
    formatted = format_sql(sql)
    if not formatted:
        return False, "SQL 为空"
    if formatted.upper() == "UNSUPPORTED":
        return False, "当前问题超出数据库问答范围"

    clean_upper = strip_comments(formatted).upper()
    if ";" in clean_upper:
        return False, "只允许单条 SELECT 查询"
    if not clean_upper.startswith("SELECT"):
        return False, "只允许 SELECT 查询"

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword_present(clean_upper, keyword):
            return False, f"SQL 包含禁止关键字: {keyword}"

    if "TENANT_ID" not in clean_upper:
        return False, "SQL 必须包含 tenant_id 租户过滤"
    return True, ""


def ensure_limit(sql: str, max_rows: int = 1000) -> str:
    """补充或收紧 LIMIT，防止模型生成的大结果集拖垮只读库。"""
    formatted = format_sql(sql)
    match = re.search(r"\bLIMIT\s+(\d+)\b", formatted, flags=re.IGNORECASE)
    if not match:
        return f"{formatted} LIMIT {max_rows}"
    current_limit = int(match.group(1))
    if current_limit <= max_rows:
        return formatted
    return f"{formatted[:match.start(1)]}{max_rows}{formatted[match.end(1):]}"


def _table_aliases(sql: str) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+`?([A-Za-z_][\w]*)`?(?:\s+(?:AS\s+)?`?([A-Za-z_][\w]*)`?)?",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        table_name = match.group(1)
        alias = match.group(2) or table_name
        if alias.upper() in CLAUSE_KEYWORDS:
            alias = table_name
        aliases.append((table_name, alias))
    return aliases


def ensure_soft_delete_filters(sql: str, tables_with_is_deleted: set[str]) -> str:
    """按架构文档要求，为带 is_deleted 字段的业务表自动注入逻辑删除过滤。"""
    formatted = format_sql(sql)
    if not tables_with_is_deleted or not formatted:
        return formatted

    clean_upper = strip_comments(formatted).upper()
    conditions: list[str] = []
    for table_name, alias in _table_aliases(formatted):
        if table_name not in tables_with_is_deleted:
            continue
        alias_or_table = alias or table_name
        field_pattern = rf"\b(?:{re.escape(alias_or_table)}|{re.escape(table_name)})\s*\.\s*IS_DELETED\b"
        if re.search(field_pattern, clean_upper, flags=re.IGNORECASE):
            continue
        conditions.append(f"{alias_or_table}.is_deleted = 0")

    if not conditions:
        return formatted

    condition_sql = " AND ".join(dict.fromkeys(conditions))
    insert_match = re.search(r"\b(GROUP BY|HAVING|ORDER BY|LIMIT)\b", formatted, flags=re.IGNORECASE)
    insert_at = insert_match.start() if insert_match else len(formatted)
    head = formatted[:insert_at].rstrip()
    tail = formatted[insert_at:].lstrip()

    if re.search(r"\bWHERE\b", head, flags=re.IGNORECASE):
        merged = f"{head} AND {condition_sql}"
    else:
        merged = f"{head} WHERE {condition_sql}"
    return f"{merged} {tail}".strip()
