from app.modules.rag.retrieval_service import _build_citations, _build_context
from app.modules.rag.schemas import RagHit, RagSearchResponse


def test_rag_search_response_builds_stable_knowledge_citations():
    hits = [
        RagHit(
            citation_id="K1",
            source_type="document",
            doc_id="doc_sales_sop",
            section_id="sec_quote",
            title="报价跟进 SOP",
            text="报价后 24 小时内应确认客户是否收到，并补充 ROI 说明。",
            score=0.92,
            rank_no=1,
        ),
        RagHit(
            citation_id="K2",
            source_type="qa",
            doc_id="qa_objection",
            section_id=None,
            title="QA 问答对",
            text="问题：客户觉得贵怎么办？\n答案：先确认预算区间，再强调投入产出。",
            score=0.81,
            rank_no=2,
        ),
    ]

    citations = _build_citations(hits)
    context = _build_context(hits)
    response = RagSearchResponse(
        trace_id="trace_citation_v1",
        question="客户觉得报价贵，如何跟进？",
        rewritten_query="客户觉得报价贵，如何跟进？ 价格太贵 预算不足 异议处理",
        hits=hits,
        citations=citations,
        answer_context=context,
    )

    assert response.citations[0].citation_id == "K1"
    assert response.citations[0].ref == "doc_sales_sop#sec_quote"
    assert response.citations[0].text_preview.startswith("报价后 24 小时")
    assert response.citations[1].ref == "qa_objection"
    assert "[K1]" in response.answer_context
    assert "[K2]" in response.answer_context
    assert response.hits[0].citation_id == response.citations[0].citation_id
