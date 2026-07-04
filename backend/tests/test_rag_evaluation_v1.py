from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.evaluation import service


def _cleanup_rag_eval_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM rag_evaluation_result WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_case WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM evaluation_dataset WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_rag_evaluation_records_retrieval_quality_summary():
    tenant_id = "tenant_rag_eval_v1"
    user_id = "u_rag_eval"
    _cleanup_rag_eval_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            dataset = service.create_dataset(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                name="RAG 检索召回评测集",
                description="用于统计知识检索 Recall@K、MRR 和 NDCG",
                target_type="rag",
                metadata_json={"top_k": 5},
            )
            hit_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="命中产品说明章节",
                user_input="InsightPilot 支持哪些企业级智能体能力？",
                expected_behavior="TopK 内应命中产品说明文档的能力章节",
                target_type="rag",
                target_name="rag.search",
                tags=["recall", "knowledge"],
                metadata_json={"expected_doc_id": "doc_product", "expected_section_id": "sec_agent"},
            )
            miss_case = service.create_case(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                dataset_id=dataset["dataset_id"],
                title="未命中权限说明章节",
                user_input="系统如何隔离租户权限？",
                expected_behavior="TopK 内应命中权限设计章节",
                target_type="rag",
                target_name="rag.search",
                tags=["miss"],
                metadata_json={"expected_doc_id": "doc_auth", "expected_section_id": "sec_tenant"},
            )
            hit_result = service.create_rag_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=hit_case["case_id"],
                trace_id="trace_rag_hit",
                top_k=5,
                hit_count=1,
                expected_doc_id="doc_product",
                expected_section_id="sec_agent",
                matched_rank=2,
                recall_hit=True,
                mrr_score=0.5,
                ndcg_score=0.63093,
                rerank_enabled=True,
                rerank_ms=30,
                elapsed_ms=120,
                metadata_json={"top_hits": [{"doc_id": "doc_product", "section_id": "sec_agent", "rank_no": 2}]},
            )
            service.create_rag_evaluation_result(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                case_id=miss_case["case_id"],
                trace_id="trace_rag_miss",
                top_k=5,
                hit_count=0,
                expected_doc_id="doc_auth",
                expected_section_id="sec_tenant",
                matched_rank=None,
                recall_hit=False,
                mrr_score=0,
                ndcg_score=0,
                rerank_enabled=False,
                rerank_ms=0,
                elapsed_ms=80,
                metadata_json={"top_hits": [{"doc_id": "doc_product", "section_id": "sec_agent", "rank_no": 1}]},
            )
            summary = service.summarize_rag_evaluation(
                db,
                tenant_id=tenant_id,
                dataset_id=dataset["dataset_id"],
            )

        assert hit_result["recall_hit"] is True
        assert hit_result["matched_rank"] == 2
        assert hit_result["metadata_json"]["top_hits"][0]["doc_id"] == "doc_product"
        assert summary["total_count"] == 2
        assert summary["hit_count"] == 1
        assert summary["recall_at_k"] == 0.5
        assert summary["total_hit_count"] == 1
        assert summary["avg_mrr"] == 0.25
        assert summary["avg_ndcg"] == 0.3155
        assert summary["avg_elapsed_ms"] == 100
        assert summary["avg_rerank_ms"] == 15
        assert summary["latest_misses"][0]["trace_id"] == "trace_rag_miss"
        assert summary["latest_misses"][0]["metadata_json"]["top_hits"][0]["rank_no"] == 1
    finally:
        _cleanup_rag_eval_fixture(tenant_id)
