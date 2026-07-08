from app.modules.memory import conversation_fact_service


def extract_customer_long_term_facts(tenant_id: str, user_id: str, extract_job_id: str) -> dict:
    """RQ Worker 入口：从对话窗口中提取稳定长期事实，再安全补入原子长期记忆层。"""
    return conversation_fact_service.run_conversation_long_term_fact_extraction_job(
        tenant_id=tenant_id,
        user_id=user_id,
        extract_job_id=extract_job_id,
    )
