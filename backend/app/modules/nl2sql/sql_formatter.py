import re


def strip_code_fence(text: str) -> str:
    """剥离 LLM 可能返回的 Markdown 代码块，只保留 SQL 文本。"""
    raw = str(text or "").strip()
    if not raw.startswith("```"):
        return raw
    raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def normalize_question(question: str) -> str:
    return " ".join(str(question or "").lower().split()).strip()


def format_sql(sql: str) -> str:
    """轻量 SQL 美化；未引入 sqlparse 时也保持关键字和空白稳定。"""
    formatted = strip_code_fence(sql).strip().rstrip(";")
    if not formatted:
        return ""
    formatted = re.sub(r"\s+", " ", formatted)
    for keyword in ["select", "from", "where", "group by", "order by", "having", "limit", "left join", "join"]:
        formatted = re.sub(rf"\b{keyword}\b", keyword.upper(), formatted, flags=re.IGNORECASE)
    return formatted
