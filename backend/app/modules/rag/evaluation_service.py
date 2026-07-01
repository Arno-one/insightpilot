import json
import math
import time
from pathlib import Path

from app.core.config import settings
from app.modules.rag.retrieval_service import search_knowledge


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _docs_dir() -> Path:
    configured = Path(settings.rag_docs_dir)
    if configured.is_absolute():
        return configured
    return _project_root() / configured


def _find_qa_file(root: Path) -> Path:
    files = list(root.glob("*QA*.jsonl.md")) or list(root.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError("未找到 QA JSONL 评估文件")
    return files[0]


def _load_eval_cases(limit: int) -> list[dict]:
    """读取 QA 数据集作为检索评估集；V1 用 QA 的来源章节作为标准答案。"""
    qa_file = _find_qa_file(_docs_dir())
    cases = []
    for line in qa_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cases.append(
            {
                "case_id": row["id"],
                "question": row["question"],
                "expected_doc_id": row["doc_id"],
                "expected_section_id": row["section_id"],
            }
        )
        if len(cases) >= limit:
            break
    return cases


def _find_relevant_rank(hits: list, expected_doc_id: str, expected_section_id: str) -> int | None:
    """查找期望 doc_id + section_id 在 TopK 中的排名，排名从 1 开始。"""
    for hit in hits:
        if hit.doc_id == expected_doc_id and hit.section_id == expected_section_id:
            return hit.rank_no
    return None


def _ndcg_for_rank(rank: int | None) -> float:
    if rank is None:
        return 0.0
    # 中文注释：单相关答案场景下 IDCG=1，因此 NDCG 等于 1/log2(rank+1)。
    return 1 / math.log2(rank + 1)


def evaluate_rag_retrieval(
    tenant_id: str,
    user_id: str,
    top_k: int = 5,
    limit: int = 20,
    enable_rerank: bool = True,
) -> dict:
    """执行 RAG 检索离线评估，输出 Recall@K、MRR、NDCG 和逐条明细。"""
    started = time.time()
    cases = _load_eval_cases(limit)
    details = []
    hit_count = 0
    reciprocal_rank_sum = 0.0
    ndcg_sum = 0.0

    for case in cases:
        result = search_knowledge(
            tenant_id=tenant_id,
            user_id=user_id,
            question=case["question"],
            top_k=top_k,
            enable_rerank=enable_rerank,
        )
        rank = _find_relevant_rank(result.hits, case["expected_doc_id"], case["expected_section_id"])
        is_hit = rank is not None
        if is_hit:
            hit_count += 1
            reciprocal_rank_sum += 1 / rank
        ndcg = _ndcg_for_rank(rank)
        ndcg_sum += ndcg
        details.append(
            {
                **case,
                "trace_id": result.trace_id,
                "hit": is_hit,
                "rank": rank,
                "mrr_score": 1 / rank if rank else 0.0,
                "ndcg_score": ndcg,
                "top_hits": [
                    {
                        "rank_no": hit.rank_no,
                        "source_type": hit.source_type,
                        "doc_id": hit.doc_id,
                        "section_id": hit.section_id,
                        "title": hit.title,
                    }
                    for hit in result.hits
                ],
            }
        )

    total = len(cases) or 1
    return {
        "top_k": top_k,
        "case_count": len(cases),
        "hit_count": hit_count,
        "recall_at_k": round(hit_count / total, 4),
        "mrr": round(reciprocal_rank_sum / total, 4),
        "ndcg": round(ndcg_sum / total, 4),
        "duration_ms": int((time.time() - started) * 1000),
        "details": details,
    }
