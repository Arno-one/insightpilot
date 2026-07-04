import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.rag.embedding_client import embed_query
from app.modules.rag.milvus_client import ensure_collections, get_milvus_client, hybrid_search
from app.modules.rag.schemas import RagCitation, RagHit, RagSearchResponse
from app.shared.ids import new_id

logger = logging.getLogger(__name__)


def rewrite_query(question: str) -> str:
    """轻量查询改写：V1 先规则增强，后续可替换为 LLM Rewrite。"""
    q = question.strip()
    expansions = {
        "嫌贵": "价格太贵 预算不足 异议处理",
        "不回复": "报价后无回应 长时间不回复 流失风险",
        "竞品": "竞品介入 竞品比较 价值差异",
        "AI不可靠": "AI 不可靠 人工确认 规则引擎 审计日志",
        "数据安全": "数据安全 RBAC 权限控制 Agent 工具权限",
    }
    extra = [value for key, value in expansions.items() if key in q]
    return f"{q} {' '.join(extra)}".strip()


def _entity(hit: dict) -> dict:
    entity = hit.get("entity") if isinstance(hit, dict) else None
    return entity or hit


def _score(hit: dict) -> float | None:
    for key in ["distance", "score"]:
        if isinstance(hit, dict) and key in hit:
            try:
                return float(hit[key])
            except Exception:
                return None
    return None


def _normalize_hit(hit: dict, source_collection: str, rank_no: int) -> RagHit:
    entity = _entity(hit)
    source_type = entity.get("source_type") or ("qa" if source_collection == settings.rag_qa_collection else "document")
    if source_type == "qa":
        text_value = f"问题：{entity.get('question', '')}\n答案：{entity.get('answer', '')}"
        title = "QA 问答对"
    else:
        text_value = entity.get("text", "")
        title = entity.get("title")
    return RagHit(
        source_type=source_type,
        doc_id=entity.get("doc_id", ""),
        section_id=entity.get("section_id"),
        title=title,
        text=text_value,
        score=_score(hit),
        rank_no=rank_no,
    )


def _dedupe_hits(hits: list[RagHit]) -> list[RagHit]:
    """按 doc_id + section_id + 文本前缀去重，优先保留排序靠前结果。"""
    seen: set[tuple[str, str | None, str]] = set()
    result: list[RagHit] = []
    for hit in hits:
        key = (hit.doc_id, hit.section_id, hit.text[:80])
        if key in seen:
            continue
        seen.add(key)
        result.append(hit)
    return result


def _citation_ref(hit: RagHit) -> str:
    return f"{hit.doc_id}#{hit.section_id}" if hit.section_id else hit.doc_id


def _build_citations(hits: list[RagHit]) -> list[RagCitation]:
    citations: list[RagCitation] = []
    for index, hit in enumerate(hits, 1):
        citation_id = hit.citation_id or f"K{index}"
        citations.append(
            RagCitation(
                citation_id=citation_id,
                source_type=hit.source_type,
                doc_id=hit.doc_id,
                section_id=hit.section_id,
                title=hit.title,
                rank_no=hit.rank_no,
                score=hit.score,
                ref=_citation_ref(hit),
                text_preview=hit.text[:300],
            )
        )
    return citations


def _build_context(hits: list[RagHit], max_chars: int = 3000) -> str:
    parts = []
    used = 0
    for index, hit in enumerate(hits, 1):
        # 中文注释：上下文中的 K 编号与 citations 一一对应，便于 Agent 在回答中稳定引用来源。
        citation_id = hit.citation_id or f"K{index}"
        block = f"[{citation_id}] ({hit.source_type}) {hit.doc_id}/{hit.section_id or '-'}\n{hit.text}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _insert_trace(db: Session, tenant_id: str, user_id: str, trace_id: str, question: str, rewritten: str, timings: dict, hits: list[RagHit]) -> None:
    db.execute(
        text(
            """
            INSERT INTO rag_retrieval_trace (
              tenant_id, trace_id, user_id, original_query, rewritten_query, strategy,
              rewrite_ms, embed_ms, search_ms, rerank_ms, total_ms, top_k, hit_count
            )
            VALUES (
              :tenant_id, :trace_id, :user_id, :original_query, :rewritten_query, :strategy,
              :rewrite_ms, :embed_ms, :search_ms, :rerank_ms, :total_ms, :top_k, :hit_count
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "user_id": user_id,
            "original_query": question,
            "rewritten_query": rewritten,
            "strategy": "rewrite+dense+bm25+rrf",
            "rewrite_ms": timings.get("rewrite_ms", 0),
            "embed_ms": timings.get("embed_ms", 0),
            "search_ms": timings.get("search_ms", 0),
            "rerank_ms": timings.get("rerank_ms", 0),
            "total_ms": timings.get("total_ms", 0),
            "top_k": len(hits),
            "hit_count": len(hits),
        },
    )
    for hit in hits:
        db.execute(
            text(
                """
                INSERT INTO rag_retrieval_hit (
                  tenant_id, trace_id, hit_id, source_collection, source_type, doc_id, section_id,
                  rank_no, rrf_score, text_preview
                )
                VALUES (
                  :tenant_id, :trace_id, :hit_id, :source_collection, :source_type, :doc_id, :section_id,
                  :rank_no, :rrf_score, :text_preview
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "hit_id": new_id("hit"),
                "source_collection": settings.rag_qa_collection if hit.source_type == "qa" else settings.rag_document_collection,
                "source_type": hit.source_type,
                "doc_id": hit.doc_id,
                "section_id": hit.section_id,
                "rank_no": hit.rank_no,
                "rrf_score": hit.score,
                "text_preview": hit.text[:800],
            },
        )


def search_knowledge(tenant_id: str, user_id: str, question: str, top_k: int = 5, enable_rerank: bool = True) -> RagSearchResponse:
    """执行在线 RAG 检索，返回可供 Agent 组装 Prompt 的上下文。"""
    total_start = time.time()
    timings: dict[str, int] = {}

    t0 = time.time()
    rewritten = rewrite_query(question)
    timings["rewrite_ms"] = int((time.time() - t0) * 1000)

    t0 = time.time()
    query_vector = embed_query(rewritten)
    timings["embed_ms"] = int((time.time() - t0) * 1000)

    client = get_milvus_client()
    ensure_collections(client)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=2) as executor:
        doc_future = executor.submit(hybrid_search, settings.rag_document_collection, rewritten, query_vector, tenant_id, top_k)
        qa_future = executor.submit(hybrid_search, settings.rag_qa_collection, rewritten, query_vector, tenant_id, top_k)
        doc_hits = doc_future.result()
        qa_hits = qa_future.result()
    timings["search_ms"] = int((time.time() - t0) * 1000)

    normalized: list[RagHit] = []
    for hit in qa_hits:
        normalized.append(_normalize_hit(hit, settings.rag_qa_collection, len(normalized) + 1))
    for hit in doc_hits:
        normalized.append(_normalize_hit(hit, settings.rag_document_collection, len(normalized) + 1))
    hits = _dedupe_hits(normalized)[:top_k]
    for index, hit in enumerate(hits, 1):
        hit.rank_no = index
        hit.citation_id = f"K{index}"

    timings["rerank_ms"] = 0
    timings["total_ms"] = int((time.time() - total_start) * 1000)
    trace_id = new_id("trace")
    context = _build_context(hits)
    citations = _build_citations(hits)

    db = SessionLocal()
    try:
        _insert_trace(db, tenant_id, user_id, trace_id, question, rewritten, timings, hits)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("RAG trace 写入失败")
    finally:
        db.close()

    return RagSearchResponse(
        trace_id=trace_id,
        question=question,
        rewritten_query=rewritten,
        hits=hits,
        citations=citations,
        answer_context=context,
    )
