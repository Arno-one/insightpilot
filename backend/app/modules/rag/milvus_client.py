import logging

from pymilvus import AnnSearchRequest, DataType, Function, FunctionType, MilvusClient, RRFRanker

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_milvus_client() -> MilvusClient:
    """创建 MilvusClient，并尽量切换到 InsightPilot 独立数据库。"""
    client = MilvusClient(uri=settings.milvus_uri)
    # 中文注释：Milvus Lite 使用本地 .db 文件时不支持 database API，跳过切库避免测试日志噪音。
    if settings.milvus_uri.lower().endswith(".db"):
        return client
    try:
        dbs = client.list_databases()
        if settings.milvus_db_name not in dbs:
            client.create_database(settings.milvus_db_name)
        client.use_database(settings.milvus_db_name)
    except Exception as exc:
        logger.warning("Milvus 数据库切换失败，继续使用默认库: %s", exc)
    return client


def _create_index_params(client: MilvusClient):
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vector",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    index_params.add_index(
        field_name="sparse_vector",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="BM25",
    )
    return index_params


def _safe_create_indexes(client: MilvusClient, collection_name: str) -> None:
    """创建索引；Milvus Lite 在 Windows 上偶发 manifest 冲突，测试环境允许降级。"""
    try:
        client.create_index(collection_name=collection_name, index_params=_create_index_params(client))
    except Exception as exc:
        logger.warning("Milvus 索引创建失败，继续使用集合默认能力 collection=%s: %s", collection_name, exc)


def ensure_document_collection(client: MilvusClient) -> None:
    if client.has_collection(settings.rag_document_collection):
        return
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=100)
    schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
    schema.add_field("doc_id", DataType.VARCHAR, max_length=80)
    schema.add_field("section_id", DataType.VARCHAR, max_length=80)
    schema.add_field("category", DataType.VARCHAR, max_length=50)
    schema.add_field("title", DataType.VARCHAR, max_length=200)
    schema.add_field("text", DataType.VARCHAR, max_length=4000, enable_analyzer=True, enable_match=True)
    schema.add_field("chunk_index", DataType.INT64)
    schema.add_field("source_file", DataType.VARCHAR, max_length=255)
    schema.add_field("source_type", DataType.VARCHAR, max_length=30)
    schema.add_field("created_at", DataType.INT64)
    schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=settings.embedding_dimension)
    schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_function(
        Function(
            name="document_text_bm25",
            input_field_names=["text"],
            output_field_names=["sparse_vector"],
            function_type=FunctionType.BM25,
        )
    )
    client.create_collection(
        collection_name=settings.rag_document_collection,
        schema=schema,
    )
    _safe_create_indexes(client, settings.rag_document_collection)


def ensure_qa_collection(client: MilvusClient) -> None:
    if client.has_collection(settings.rag_qa_collection):
        return
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=100)
    schema.add_field("tenant_id", DataType.VARCHAR, max_length=64)
    schema.add_field("qa_id", DataType.VARCHAR, max_length=100)
    schema.add_field("doc_id", DataType.VARCHAR, max_length=80)
    schema.add_field("section_id", DataType.VARCHAR, max_length=80)
    schema.add_field("question", DataType.VARCHAR, max_length=1000)
    schema.add_field("answer", DataType.VARCHAR, max_length=3000)
    schema.add_field("tags", DataType.VARCHAR, max_length=1000)
    schema.add_field("search_text", DataType.VARCHAR, max_length=5000, enable_analyzer=True, enable_match=True)
    schema.add_field("source_type", DataType.VARCHAR, max_length=30)
    schema.add_field("created_at", DataType.INT64)
    schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=settings.embedding_dimension)
    schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_function(
        Function(
            name="qa_search_text_bm25",
            input_field_names=["search_text"],
            output_field_names=["sparse_vector"],
            function_type=FunctionType.BM25,
        )
    )
    client.create_collection(
        collection_name=settings.rag_qa_collection,
        schema=schema,
    )
    _safe_create_indexes(client, settings.rag_qa_collection)


def ensure_collections(client: MilvusClient) -> None:
    ensure_document_collection(client)
    ensure_qa_collection(client)
    client.load_collection(settings.rag_document_collection)
    client.load_collection(settings.rag_qa_collection)


def delete_tenant_data(client: MilvusClient, tenant_id: str) -> None:
    """重复入库前清理当前租户旧向量，避免演示数据重复。"""
    for collection in [settings.rag_document_collection, settings.rag_qa_collection]:
        if client.has_collection(collection):
            try:
                client.delete(collection_name=collection, filter=f'tenant_id == "{tenant_id}"')
            except Exception as exc:
                logger.warning("清理 Milvus 旧数据失败 collection=%s: %s", collection, exc)


def hybrid_search(collection_name: str, query: str, query_vector: list[float], tenant_id: str, top_k: int) -> list[dict]:
    client = get_milvus_client()
    text_field = "search_text" if collection_name == settings.rag_qa_collection else "text"
    req_dense = AnnSearchRequest(
        data=[query_vector],
        anns_field="dense_vector",
        param={"metric_type": "COSINE"},
        limit=top_k,
        filter=f'tenant_id == "{tenant_id}"',
    )
    req_sparse = AnnSearchRequest(
        data=[query],
        anns_field="sparse_vector",
        param={"metric_type": "BM25"},
        limit=top_k,
        filter=f'tenant_id == "{tenant_id}"',
    )
    if collection_name == settings.rag_qa_collection:
        output_fields = ["tenant_id", "qa_id", "doc_id", "section_id", "source_type", "question", "answer", "tags", "search_text"]
    else:
        output_fields = ["tenant_id", "doc_id", "section_id", "source_type", "title", "text", "chunk_index", "source_file"]
    results = client.hybrid_search(
        collection_name=collection_name,
        reqs=[req_dense, req_sparse],
        ranker=RRFRanker(k=60),
        limit=top_k,
        output_fields=output_fields,
    )
    return list(results[0]) if results else []
