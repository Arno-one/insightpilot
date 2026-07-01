from fastapi import APIRouter, Depends

from app.core.queue import get_default_queue
from app.modules.auth.dependencies import require_permission
from app.modules.rag.retrieval_service import search_knowledge
from app.modules.rag.schemas import RagSearchRequest
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


@router.post("/search")
def search_rag(
    data: RagSearchRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    result = search_knowledge(
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        question=data.question,
        top_k=data.top_k,
        enable_rerank=data.enable_rerank,
    )
    return success(result.model_dump(), "检索成功", total=len(result.hits))
