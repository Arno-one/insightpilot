import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.ids import new_id


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _loads(value: Any):
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {} if value is None else value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _row_to_dataset(row) -> dict:
    item = dict(row)
    item["metadata_json"] = _loads(item.get("metadata_json")) or {}
    return item


def _row_to_case(row) -> dict:
    item = dict(row)
    item["tags"] = _loads(item.pop("tags_json", None)) or []
    item["metadata_json"] = _loads(item.get("metadata_json")) or {}
    return item


def create_dataset(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    name: str,
    description: str | None,
    target_type: str,
    metadata_json: dict | None = None,
) -> dict:
    dataset_id = new_id("evalds")
    db.execute(
        text(
            """
            INSERT INTO evaluation_dataset (
              tenant_id, dataset_id, name, description, target_type, metadata_json, created_by_user_id
            )
            VALUES (
              :tenant_id, :dataset_id, :name, :description, :target_type, :metadata_json, :created_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "dataset_id": dataset_id,
            "name": name,
            "description": description,
            "target_type": target_type,
            "metadata_json": _dumps(metadata_json),
            "created_by_user_id": user_id,
        },
    )
    db.commit()
    return get_dataset(db, tenant_id=tenant_id, dataset_id=dataset_id)


def get_dataset(db: Session, *, tenant_id: str, dataset_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT dataset_id, tenant_id, name, description, target_type, status,
                   metadata_json, created_by_user_id, created_at, updated_at
            FROM evaluation_dataset
            WHERE tenant_id = :tenant_id AND dataset_id = :dataset_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "dataset_id": dataset_id},
    ).mappings().first()
    if not row:
        raise ValueError("评测数据集不存在")
    return _row_to_dataset(row)


def list_datasets(db: Session, *, tenant_id: str, target_type: str | None = None, limit: int = 100) -> list[dict]:
    filters = ["tenant_id = :tenant_id"]
    params = {"tenant_id": tenant_id, "target_type": target_type, "limit": max(1, min(limit, 500))}
    if target_type:
        filters.append("target_type = :target_type")
    rows = db.execute(
        text(
            f"""
            SELECT dataset_id, tenant_id, name, description, target_type, status,
                   metadata_json, created_by_user_id, created_at, updated_at
            FROM evaluation_dataset
            WHERE {' AND '.join(filters)}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_row_to_dataset(row) for row in rows]


def create_case(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    dataset_id: str,
    title: str,
    user_input: str,
    expected_behavior: str,
    target_type: str,
    target_name: str,
    tags: list[str] | None = None,
    metadata_json: dict | None = None,
) -> dict:
    # 中文注释：创建 case 前先校验 dataset 属于当前租户，避免跨租户挂载评测样本。
    get_dataset(db, tenant_id=tenant_id, dataset_id=dataset_id)
    case_id = new_id("evalcase")
    db.execute(
        text(
            """
            INSERT INTO evaluation_case (
              tenant_id, case_id, dataset_id, title, user_input, expected_behavior,
              target_type, target_name, tags_json, metadata_json, created_by_user_id
            )
            VALUES (
              :tenant_id, :case_id, :dataset_id, :title, :user_input, :expected_behavior,
              :target_type, :target_name, :tags_json, :metadata_json, :created_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "dataset_id": dataset_id,
            "title": title,
            "user_input": user_input,
            "expected_behavior": expected_behavior,
            "target_type": target_type,
            "target_name": target_name,
            "tags_json": json.dumps(tags or [], ensure_ascii=False, default=str),
            "metadata_json": _dumps(metadata_json),
            "created_by_user_id": user_id,
        },
    )
    db.commit()
    return get_case(db, tenant_id=tenant_id, case_id=case_id)


def get_case(db: Session, *, tenant_id: str, case_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT case_id, tenant_id, dataset_id, title, user_input, expected_behavior,
                   target_type, target_name, tags_json, metadata_json, status,
                   created_by_user_id, created_at, updated_at
            FROM evaluation_case
            WHERE tenant_id = :tenant_id AND case_id = :case_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "case_id": case_id},
    ).mappings().first()
    if not row:
        raise ValueError("评测样本不存在")
    return _row_to_case(row)


def list_cases(
    db: Session,
    *,
    tenant_id: str,
    dataset_id: str | None = None,
    target_type: str | None = None,
    target_name: str | None = None,
    limit: int = 100,
) -> list[dict]:
    filters = ["tenant_id = :tenant_id"]
    params = {
        "tenant_id": tenant_id,
        "dataset_id": dataset_id,
        "target_type": target_type,
        "target_name": target_name,
        "limit": max(1, min(limit, 500)),
    }
    if dataset_id:
        filters.append("dataset_id = :dataset_id")
    if target_type:
        filters.append("target_type = :target_type")
    if target_name:
        filters.append("target_name = :target_name")
    rows = db.execute(
        text(
            f"""
            SELECT case_id, tenant_id, dataset_id, title, user_input, expected_behavior,
                   target_type, target_name, tags_json, metadata_json, status,
                   created_by_user_id, created_at, updated_at
            FROM evaluation_case
            WHERE {' AND '.join(filters)}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    return [_row_to_case(row) for row in rows]


def _row_to_nl2sql_result(row) -> dict:
    item = dict(row)
    item["metadata_json"] = _loads(item.get("metadata_json")) or {}
    return item


def _row_to_rag_result(row) -> dict:
    item = dict(row)
    item["recall_hit"] = bool(item.get("recall_hit"))
    item["rerank_enabled"] = bool(item.get("rerank_enabled"))
    item["mrr_score"] = float(item.get("mrr_score") or 0)
    item["ndcg_score"] = float(item.get("ndcg_score") or 0)
    item["metadata_json"] = _loads(item.get("metadata_json")) or {}
    return item


def create_nl2sql_evaluation_result(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    case_id: str,
    query_id: str | None,
    generated_sql: str | None,
    status: str,
    row_count: int,
    error_message: str | None = None,
    elapsed_ms: int = 0,
    metadata_json: dict | None = None,
) -> dict:
    case = get_case(db, tenant_id=tenant_id, case_id=case_id)
    if case["target_type"] != "nl2sql":
        raise ValueError("评测样本不是 NL2SQL 类型")
    result_id = new_id("evalres")
    db.execute(
        text(
            """
            INSERT INTO nl2sql_evaluation_result (
              tenant_id, result_id, dataset_id, case_id, query_id, generated_sql,
              status, row_count, error_message, elapsed_ms, metadata_json, created_by_user_id
            )
            VALUES (
              :tenant_id, :result_id, :dataset_id, :case_id, :query_id, :generated_sql,
              :status, :row_count, :error_message, :elapsed_ms, :metadata_json, :created_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "result_id": result_id,
            "dataset_id": case["dataset_id"],
            "case_id": case_id,
            "query_id": query_id,
            "generated_sql": generated_sql,
            "status": status,
            "row_count": row_count,
            "error_message": error_message,
            "elapsed_ms": elapsed_ms,
            "metadata_json": _dumps(metadata_json),
            "created_by_user_id": user_id,
        },
    )
    db.commit()
    return get_nl2sql_evaluation_result(db, tenant_id=tenant_id, result_id=result_id)


def get_nl2sql_evaluation_result(db: Session, *, tenant_id: str, result_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT result_id, tenant_id, dataset_id, case_id, query_id, generated_sql,
                   status, row_count, error_message, elapsed_ms, metadata_json,
                   created_by_user_id, created_at
            FROM nl2sql_evaluation_result
            WHERE tenant_id = :tenant_id AND result_id = :result_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "result_id": result_id},
    ).mappings().first()
    if not row:
        raise ValueError("NL2SQL 评测结果不存在")
    return _row_to_nl2sql_result(row)


def summarize_nl2sql_evaluation(db: Session, *, tenant_id: str, dataset_id: str | None = None) -> dict:
    filters = ["tenant_id = :tenant_id"]
    params = {"tenant_id": tenant_id, "dataset_id": dataset_id}
    if dataset_id:
        filters.append("dataset_id = :dataset_id")
    row = db.execute(
        text(
            f"""
            SELECT COUNT(*) AS total_count,
                   SUM(CASE WHEN status = 'executed' THEN 1 ELSE 0 END) AS success_count,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                   COALESCE(SUM(row_count), 0) AS total_row_count,
                   COALESCE(AVG(elapsed_ms), 0) AS avg_elapsed_ms
            FROM nl2sql_evaluation_result
            WHERE {' AND '.join(filters)}
            """
        ),
        params,
    ).mappings().first()
    latest_errors = db.execute(
        text(
            f"""
            SELECT result_id, case_id, error_message, created_at
            FROM nl2sql_evaluation_result
            WHERE {' AND '.join(filters)}
              AND status = 'failed'
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """
        ),
        params,
    ).mappings().all()
    total_count = int(row["total_count"] or 0)
    success_count = int(row["success_count"] or 0)
    failed_count = int(row["failed_count"] or 0)
    return {
        "dataset_id": dataset_id,
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": round(success_count / total_count, 4) if total_count else 0,
        "total_row_count": int(row["total_row_count"] or 0),
        "avg_elapsed_ms": round(float(row["avg_elapsed_ms"] or 0), 2),
        "latest_errors": [dict(item) for item in latest_errors],
    }


def create_rag_evaluation_result(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    case_id: str,
    trace_id: str | None = None,
    top_k: int = 5,
    hit_count: int = 0,
    expected_doc_id: str | None = None,
    expected_section_id: str | None = None,
    matched_rank: int | None = None,
    recall_hit: bool = False,
    mrr_score: float = 0,
    ndcg_score: float = 0,
    rerank_enabled: bool = True,
    rerank_ms: int = 0,
    elapsed_ms: int = 0,
    metadata_json: dict | None = None,
) -> dict:
    case = get_case(db, tenant_id=tenant_id, case_id=case_id)
    if case["target_type"] != "rag":
        raise ValueError("评测样本不是 RAG 类型")
    result_id = new_id("rageval")
    db.execute(
        text(
            """
            INSERT INTO rag_evaluation_result (
              tenant_id, result_id, dataset_id, case_id, trace_id, top_k, hit_count,
              expected_doc_id, expected_section_id, matched_rank, recall_hit,
              mrr_score, ndcg_score, rerank_enabled, rerank_ms, elapsed_ms,
              metadata_json, created_by_user_id
            )
            VALUES (
              :tenant_id, :result_id, :dataset_id, :case_id, :trace_id, :top_k, :hit_count,
              :expected_doc_id, :expected_section_id, :matched_rank, :recall_hit,
              :mrr_score, :ndcg_score, :rerank_enabled, :rerank_ms, :elapsed_ms,
              :metadata_json, :created_by_user_id
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "result_id": result_id,
            "dataset_id": case["dataset_id"],
            "case_id": case_id,
            "trace_id": trace_id,
            "top_k": top_k,
            "hit_count": hit_count,
            "expected_doc_id": expected_doc_id,
            "expected_section_id": expected_section_id,
            "matched_rank": matched_rank,
            "recall_hit": 1 if recall_hit else 0,
            "mrr_score": mrr_score,
            "ndcg_score": ndcg_score,
            "rerank_enabled": 1 if rerank_enabled else 0,
            "rerank_ms": rerank_ms,
            "elapsed_ms": elapsed_ms,
            "metadata_json": _dumps(metadata_json),
            "created_by_user_id": user_id,
        },
    )
    db.commit()
    return get_rag_evaluation_result(db, tenant_id=tenant_id, result_id=result_id)


def get_rag_evaluation_result(db: Session, *, tenant_id: str, result_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT result_id, tenant_id, dataset_id, case_id, trace_id, top_k, hit_count,
                   expected_doc_id, expected_section_id, matched_rank, recall_hit,
                   mrr_score, ndcg_score, rerank_enabled, rerank_ms, elapsed_ms,
                   metadata_json, created_by_user_id, created_at
            FROM rag_evaluation_result
            WHERE tenant_id = :tenant_id AND result_id = :result_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "result_id": result_id},
    ).mappings().first()
    if not row:
        raise ValueError("RAG 评测结果不存在")
    return _row_to_rag_result(row)


def summarize_rag_evaluation(db: Session, *, tenant_id: str, dataset_id: str | None = None) -> dict:
    filters = ["tenant_id = :tenant_id"]
    params = {"tenant_id": tenant_id, "dataset_id": dataset_id}
    if dataset_id:
        filters.append("dataset_id = :dataset_id")
    row = db.execute(
        text(
            f"""
            SELECT COUNT(*) AS total_count,
                   COALESCE(SUM(CASE WHEN recall_hit = 1 THEN 1 ELSE 0 END), 0) AS hit_result_count,
                   COALESCE(SUM(hit_count), 0) AS total_hit_count,
                   COALESCE(AVG(mrr_score), 0) AS avg_mrr,
                   COALESCE(AVG(ndcg_score), 0) AS avg_ndcg,
                   COALESCE(AVG(elapsed_ms), 0) AS avg_elapsed_ms,
                   COALESCE(AVG(rerank_ms), 0) AS avg_rerank_ms
            FROM rag_evaluation_result
            WHERE {' AND '.join(filters)}
            """
        ),
        params,
    ).mappings().first()
    latest_misses = db.execute(
        text(
            f"""
            SELECT result_id, case_id, trace_id, top_k, expected_doc_id,
                   expected_section_id, created_at, metadata_json
            FROM rag_evaluation_result
            WHERE {' AND '.join(filters)}
              AND recall_hit = 0
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """
        ),
        params,
    ).mappings().all()
    total_count = int(row["total_count"] or 0)
    hit_result_count = int(row["hit_result_count"] or 0)
    return {
        "dataset_id": dataset_id,
        "total_count": total_count,
        "hit_count": hit_result_count,
        "recall_at_k": round(hit_result_count / total_count, 4) if total_count else 0,
        "total_hit_count": int(row["total_hit_count"] or 0),
        "avg_mrr": round(float(row["avg_mrr"] or 0), 4),
        "avg_ndcg": round(float(row["avg_ndcg"] or 0), 4),
        "avg_elapsed_ms": round(float(row["avg_elapsed_ms"] or 0), 2),
        "avg_rerank_ms": round(float(row["avg_rerank_ms"] or 0), 2),
        "latest_misses": [
            {**dict(item), "metadata_json": _loads(item.get("metadata_json")) or {}}
            for item in latest_misses
        ],
    }
