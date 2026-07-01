from fastapi import APIRouter, Depends

from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.shared.response import success

router = APIRouter()


@router.post("/ingest")
def ingest_rag(current_user: dict = Depends(require_permission("rag:ingest:run"))):
    """提交 RAG 入库任务，具体切片、Embedding、Milvus 写入由 Worker 执行。"""
    queue = get_default_queue()
    job = queue.enqueue(
        "app.workers.rag_jobs.ingest_default_knowledge_base",
        current_user["tenant_id"],
        current_user["user_id"],
        job_timeout=1800,
    )
    return success({"job_id": job.id}, "RAG 入库任务已提交")
