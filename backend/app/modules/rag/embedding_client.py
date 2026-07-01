import hashlib
import logging
import math

from app.core.config import settings

logger = logging.getLogger(__name__)


def _deterministic_vector(text: str) -> list[float]:
    """确定性降级向量：用于本地测试或 Embedding API 不可用时保持链路可跑。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for i in range(settings.embedding_dimension):
        byte = digest[i % len(digest)]
        values.append((byte / 255.0) - 0.5)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量生成 1024 维向量；优先 DashScope，失败自动降级。"""
    if not texts:
        return []

    api_key = settings.dashscope_api_key or settings.aliyun_api_key
    if settings.use_real_embedding and api_key:
        try:
            import os
            from dashscope import TextEmbedding

            os.environ.setdefault("DASHSCOPE_API_KEY", api_key)
            vectors: list[list[float]] = []
            batch_size = 10
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = TextEmbedding.call(model="text-embedding-v3", input=batch)
                if resp.status_code != 200:
                    raise RuntimeError(f"DashScope Embedding 失败: {resp.code} {resp.message}")
                vectors.extend(item["embedding"] for item in resp.output["embeddings"])
            return vectors
        except Exception as exc:
            logger.warning("真实 Embedding 不可用，降级为确定性向量: %s", exc)

    return [_deterministic_vector(text) for text in texts]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
