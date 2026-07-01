import hashlib
import json
import logging
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.rag.chunking import split_markdown
from app.modules.rag.embedding_client import embed_texts
from app.modules.rag.milvus_client import delete_tenant_data, ensure_collections, get_milvus_client
from app.shared.ids import new_id

logger = logging.getLogger(__name__)


DOC_META = {
    "01_": ("sales_sop_v1", "InsightPilot 销售 SOP 知识库", "sales_sop"),
    "02_": ("product_pricing_v1", "InsightPilot 示例产品资料与价格策略", "product_pricing"),
    "03_": ("objection_handling_v1", "InsightPilot 异议处理话术知识库", "objection_handling"),
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _docs_dir() -> Path:
    configured = Path(settings.rag_docs_dir)
    if configured.is_absolute():
        return configured
    return _project_root() / configured


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_source_docs(root: Path) -> list[Path]:
    docs = []
    for item in root.glob("*.md"):
        if item.name.startswith(("01_", "02_", "03_")):
            docs.append(item)
    return sorted(docs)


def _meta_for_file(path: Path) -> tuple[str, str, str]:
    for prefix, meta in DOC_META.items():
        if path.name.startswith(prefix):
            return meta
    raise ValueError(f"未知 RAG 文档类型: {path.name}")


def _find_qa_file(root: Path) -> Path:
    files = list(root.glob("*QA*.jsonl.md")) or list(root.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError("未找到 QA JSONL 文件")
    return files[0]


def _upsert_document_meta(db: Session, tenant_id: str, document_id: str, doc_id: str, title: str, category: str, source_file: str, checksum: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO rag_document (
              tenant_id, document_id, doc_id, title, category, source_file, source_type, version, status, checksum
            )
            VALUES (
              :tenant_id, :document_id, :doc_id, :title, :category, :source_file, 'document', 'v1', 'active', :checksum
            )
            ON DUPLICATE KEY UPDATE
              title = VALUES(title),
              category = VALUES(category),
              source_file = VALUES(source_file),
              checksum = VALUES(checksum),
              status = 'active',
              updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "doc_id": doc_id,
            "title": title,
            "category": category,
            "source_file": source_file,
            "checksum": checksum,
        },
    )


def _clear_mysql_meta(db: Session, tenant_id: str) -> None:
    db.execute(text("DELETE FROM rag_chunk WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
    db.execute(text("DELETE FROM rag_qa_pair WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})


def _insert_document_chunks(db: Session, tenant_id: str, client, root: Path) -> int:
    total = 0
    now_ms = int(time.time() * 1000)
    for doc_file in _find_source_docs(root):
        raw = doc_file.read_text(encoding="utf-8")
        doc_id, title, category = _meta_for_file(doc_file)
        document_id = f"doc_{doc_id}"
        _upsert_document_meta(db, tenant_id, document_id, doc_id, title, category, doc_file.name, _sha256(raw))
        chunks = split_markdown(doc_id, title, raw)
        vectors = embed_texts([chunk.text for chunk in chunks])

        milvus_rows = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk_id = f"chunk_{doc_id}_{chunk.chunk_index:04d}"
            pk = f"{tenant_id}_{chunk_id}"
            milvus_rows.append(
                {
                    "pk": pk,
                    "tenant_id": tenant_id,
                    "doc_id": chunk.doc_id,
                    "section_id": chunk.section_id,
                    "category": category,
                    "title": chunk.title,
                    "text": chunk.text,
                    "chunk_index": chunk.chunk_index,
                    "source_file": doc_file.name,
                    "source_type": "document",
                    "created_at": now_ms,
                    "dense_vector": vector,
                }
            )
            db.execute(
                text(
                    """
                    INSERT INTO rag_chunk (
                      tenant_id, chunk_id, document_id, doc_id, section_id, chunk_index, title,
                      text_preview, token_count, milvus_collection, milvus_pk
                    )
                    VALUES (
                      :tenant_id, :chunk_id, :document_id, :doc_id, :section_id, :chunk_index, :title,
                      :text_preview, :token_count, :milvus_collection, :milvus_pk
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "doc_id": chunk.doc_id,
                    "section_id": chunk.section_id,
                    "chunk_index": chunk.chunk_index,
                    "title": chunk.title,
                    "text_preview": chunk.text[:500],
                    "token_count": len(chunk.text),
                    "milvus_collection": settings.rag_document_collection,
                    "milvus_pk": pk,
                },
            )

        if milvus_rows:
            client.insert(collection_name=settings.rag_document_collection, data=milvus_rows)
        total += len(milvus_rows)
    return total


def _insert_qa_pairs(db: Session, tenant_id: str, client, root: Path) -> int:
    qa_file = _find_qa_file(root)
    rows = []
    for line in qa_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))

    vectors = embed_texts([" ".join([row["question"], row["answer"], " ".join(row.get("tags", []))]) for row in rows])
    now_ms = int(time.time() * 1000)
    milvus_rows = []
    for row, vector in zip(rows, vectors, strict=True):
        qa_id = row["id"]
        tags_text = " ".join(row.get("tags", []))
        search_text = f"{row['question']} {row['answer']} {tags_text}"
        pk = f"{tenant_id}_{qa_id}"
        milvus_rows.append(
            {
                "pk": pk,
                "tenant_id": tenant_id,
                "qa_id": qa_id,
                "doc_id": row["doc_id"],
                "section_id": row["section_id"],
                "question": row["question"],
                "answer": row["answer"],
                "tags": json.dumps(row.get("tags", []), ensure_ascii=False),
                "search_text": search_text,
                "source_type": "qa",
                "created_at": now_ms,
                "dense_vector": vector,
            }
        )
        db.execute(
            text(
                """
                INSERT INTO rag_qa_pair (
                  tenant_id, qa_id, doc_id, section_id, question, answer_preview,
                  tags_json, source_type, milvus_collection, milvus_pk, status
                )
                VALUES (
                  :tenant_id, :qa_id, :doc_id, :section_id, :question, :answer_preview,
                  :tags_json, 'qa', :milvus_collection, :milvus_pk, 'active'
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "qa_id": qa_id,
                "doc_id": row["doc_id"],
                "section_id": row["section_id"],
                "question": row["question"],
                "answer_preview": row["answer"][:800],
                "tags_json": json.dumps(row.get("tags", []), ensure_ascii=False),
                "milvus_collection": settings.rag_qa_collection,
                "milvus_pk": pk,
            },
        )

    if milvus_rows:
        client.insert(collection_name=settings.rag_qa_collection, data=milvus_rows)
    return len(milvus_rows)


def ingest_default_knowledge_base(tenant_id: str, user_id: str) -> dict:
    """入库默认知识库：Markdown 切片 + QA JSONL 双集合。"""
    db = SessionLocal()
    job_id = new_id("ragjob")
    root = _docs_dir()
    started = time.time()
    try:
        db.execute(
            text(
                """
                INSERT INTO rag_ingest_job (tenant_id, job_id, job_type, source_path, status, started_at)
                VALUES (:tenant_id, :job_id, 'full', :source_path, 'running', NOW())
                """
            ),
            {"tenant_id": tenant_id, "job_id": job_id, "source_path": str(root)},
        )
        client = get_milvus_client()
        ensure_collections(client)
        delete_tenant_data(client, tenant_id)
        _clear_mysql_meta(db, tenant_id)

        document_count = _insert_document_chunks(db, tenant_id, client, root)
        qa_count = _insert_qa_pairs(db, tenant_id, client, root)
        total = document_count + qa_count
        db.execute(
            text(
                """
                UPDATE rag_ingest_job
                SET status = 'success',
                    total_count = :total_count,
                    success_count = :success_count,
                    failed_count = 0,
                    finished_at = NOW()
                WHERE tenant_id = :tenant_id AND job_id = :job_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "job_id": job_id,
                "total_count": total,
                "success_count": total,
            },
        )
        db.commit()
        return {
            "job_id": job_id,
            "document_chunks": document_count,
            "qa_pairs": qa_count,
            "total": total,
            "duration_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        db.rollback()
        logger.exception("RAG 入库失败")
        try:
            db.execute(
                text(
                    """
                    UPDATE rag_ingest_job
                    SET status = 'failed', error_message = :error_message, finished_at = NOW()
                    WHERE tenant_id = :tenant_id AND job_id = :job_id
                    """
                ),
                {"tenant_id": tenant_id, "job_id": job_id, "error_message": str(exc)},
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
