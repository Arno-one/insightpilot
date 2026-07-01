import logging

from app.modules.rag.ingestion_service import ingest_default_knowledge_base as _ingest_default_knowledge_base

logger = logging.getLogger(__name__)


def ingest_default_knowledge_base(tenant_id: str, user_id: str) -> dict:
    """RAG 入库任务：切片、Embedding、Milvus 写入和 MySQL 元信息写入。"""
    logger.info("开始 RAG 入库: tenant_id=%s, user_id=%s", tenant_id, user_id)
    return _ingest_default_knowledge_base(tenant_id, user_id)
