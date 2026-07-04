from app.modules.nl2sql.schema_context import build_schema_text


SYSTEM_PROMPT = """
你是 InsightPilot 的 NL2SQL 引擎，只把中文业务问题转换为 MySQL 查询语句。
硬性规则：
1. 只允许输出 SELECT 查询；不能输出 INSERT、UPDATE、DELETE、DROP、ALTER、CREATE、TRUNCATE。
2. 所有业务查询必须包含 tenant_id 条件，租户值使用占位符 :tenant_id。
3. 如果表存在 is_deleted 字段，必须过滤 is_deleted = 0。
4. 只返回纯 SQL，不要 Markdown，不要解释。
5. 表名和字段名必须完全来自给定 Schema。
6. 默认追加 LIMIT 100，除非用户明确要求更小 TopN。
7. 无法回答或超出数据库范围时返回 UNSUPPORTED。
建议风格：
- 不使用 SELECT *，明确列出字段。
- 多表查询使用显式 JOIN ... ON。
- 歧义字段必须加表别名。
""".strip()


FEW_SHOT_EXAMPLES = [
    {
        "question": "本月高风险客户有多少个？",
        "sql": "SELECT COUNT(DISTINCT rs.customer_id) AS high_risk_customer_count FROM customer_risk_snapshot rs WHERE rs.tenant_id = :tenant_id AND rs.risk_level = 'high' LIMIT 100",
    },
    {
        "question": "按负责人统计开放商机金额排行前5名",
        "sql": "SELECT d.owner_user_id, owner.real_name AS owner_user_name, SUM(d.amount) AS open_deal_amount FROM crm_deal d LEFT JOIN sys_user owner ON owner.tenant_id = d.tenant_id AND owner.user_id = d.owner_user_id WHERE d.tenant_id = :tenant_id AND d.close_result = 'open' GROUP BY d.owner_user_id, owner.real_name ORDER BY open_deal_amount DESC LIMIT 5",
    },
    {
        "question": "最近有哪些客户长期没有跟进？",
        "sql": "SELECT c.customer_id, c.customer_name, c.owner_user_id, c.last_follow_up_at FROM crm_customer c WHERE c.tenant_id = :tenant_id AND c.last_follow_up_at IS NOT NULL ORDER BY c.last_follow_up_at ASC LIMIT 100",
    },
    {
        "question": "待审批的 AI 动作数量是多少？",
        "sql": "SELECT COUNT(*) AS pending_approval_count FROM approval_record a WHERE a.tenant_id = :tenant_id AND a.status = 'pending' LIMIT 100",
    },
    {"question": "今天天气怎么样？", "sql": "UNSUPPORTED"},
]


def build_messages(question: str, schema_text: str | None = None) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"【数据库表结构】\n{schema_text or build_schema_text()}"},
    ]
    for example in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": example["question"]})
        messages.append({"role": "assistant", "content": example["sql"]})
    messages.append({"role": "user", "content": question})
    return messages
