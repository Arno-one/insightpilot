import logging

logger = logging.getLogger(__name__)


def generate_daily_report(tenant_id: str, user_id: str) -> dict:
    """经营日报任务占位；后续接入 LangGraph 日报生成图。"""
    logger.info("开始生成经营日报: tenant_id=%s, user_id=%s", tenant_id, user_id)
    return {"tenant_id": tenant_id, "user_id": user_id, "status": "queued_for_implementation"}
