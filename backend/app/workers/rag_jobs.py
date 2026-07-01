import logging

logger = logging.getLogger(__name__)


def ingest_default_knowledge_base(tenant_id: str, user_id: str) -> dict:
    """RAG 入库任务占位；后续实现切片、Embedding、Milvus 写入和 MySQL 元信息写入。"""
    logger.info("开始 RAG 入库: tenant_id=%s, user_id=%s", tenant_id, user_id)
    return {"tenant_id": tenant_id, "user_id": user_id, "status": "queued_for_implementation"}
