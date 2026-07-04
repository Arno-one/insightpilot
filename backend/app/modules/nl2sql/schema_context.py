from sqlalchemy import inspect

from app.core.database import engine


EXCLUDE_TABLES = {
    "alembic_version",
}

TABLE_COMMENTS = {
    "crm_customer": "客户基本信息表",
    "crm_deal": "商机表",
    "crm_follow_up_record": "客户跟进记录表",
    "customer_risk_snapshot": "客户风险快照表",
    "approval_record": "AI 动作审批表",
    "sales_task": "销售任务表",
    "business_report": "经营报告表",
    "notification_record": "通知记录表",
    "agent_chat_session": "统一 Agent 对话会话表",
    "agent_chat_message": "统一 Agent 对话消息表",
    "nl2sql_session": "NL2SQL 数据问答会话表",
    "nl2sql_message": "NL2SQL 数据问答消息表",
    "nl2sql_query_audit": "NL2SQL 查询审计表",
}

EXTRA_JOIN_PATHS = [
    "crm_customer.customer_id ↔ crm_deal.customer_id — 客户与商机",
    "crm_customer.customer_id ↔ crm_follow_up_record.customer_id — 客户与跟进记录",
    "crm_customer.customer_id ↔ customer_risk_snapshot.customer_id — 客户与风险快照",
    "crm_customer.customer_id ↔ sales_task.customer_id — 客户与销售任务",
    "crm_customer.owner_user_id ↔ sys_user.user_id — 客户负责人",
    "sales_task.approval_id ↔ approval_record.approval_id — 审批转销售任务",
    "business_report.created_by_user_id ↔ sys_user.user_id — 报告创建人",
]

ENUM_MAP = {
    "customer_risk_snapshot.risk_level": "low=低风险，medium=中风险，high=高风险",
    "approval_record.status": "pending=待审批，approved=已通过，rejected=已驳回",
    "sales_task.status": "pending=待处理，in_progress=进行中，completed=已完成，cancelled=已取消",
    "crm_customer.intent_level": "low=低意向，medium=中意向，high=高意向",
}

AGG_DEFAULTS = [
    "高风险客户：customer_risk_snapshot.risk_level = 'high'",
    "活跃任务：sales_task.status IN ('pending', 'in_progress')",
    "开放商机：crm_deal.close_result = 'open'",
    "所有业务查询必须限定 tenant_id 为当前租户",
]


def build_schema_text() -> str:
    """动态反射数据库结构，并叠加 InsightPilot 业务语义说明。"""
    inspector = inspect(engine)
    table_names = [name for name in inspector.get_table_names() if name not in EXCLUDE_TABLES]
    sections: list[str] = []

    for table_name in sorted(table_names):
        comment = TABLE_COMMENTS.get(table_name, "业务数据表")
        sections.append(f"## {table_name} — {comment}")
        for column in inspector.get_columns(table_name):
            pk = " [PK]" if column.get("primary_key") else ""
            nullable = "NULL" if column.get("nullable") else "NOT NULL"
            col_comment = column.get("comment") or ""
            suffix = f" -- {col_comment}" if col_comment else ""
            sections.append(f"  {column['name']} {column['type']} {nullable}{pk}{suffix}")

        fks = inspector.get_foreign_keys(table_name)
        if fks:
            sections.append("  --- 外键 ---")
            for fk in fks:
                constrained = ", ".join(fk.get("constrained_columns") or [])
                referred = f"{fk.get('referred_table')}.{', '.join(fk.get('referred_columns') or [])}"
                sections.append(f"  FOREIGN KEY ({constrained}) → {referred}")
        sections.append("")

    sections.append("## 跨表 JOIN 路径（关键关联）")
    sections.extend([f"  {item}" for item in EXTRA_JOIN_PATHS])
    sections.append("")
    sections.append("## 枚举值与字典映射")
    sections.extend([f"  {field}: {desc}" for field, desc in ENUM_MAP.items()])
    sections.append("")
    sections.append("## 聚合口径约定")
    sections.extend([f"  {item}" for item in AGG_DEFAULTS])
    return "\n".join(sections).strip()


def get_tables_with_column(column_name: str) -> set[str]:
    """反射具备指定字段的表，用于代码层自动补齐安全过滤条件。"""
    inspector = inspect(engine)
    matched: set[str] = set()
    for table_name in inspector.get_table_names():
        if table_name in EXCLUDE_TABLES:
            continue
        columns = inspector.get_columns(table_name)
        if any(column.get("name") == column_name for column in columns):
            matched.add(table_name)
    return matched
