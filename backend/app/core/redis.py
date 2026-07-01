from app.core.config import settings


def get_redis():
    """创建 Redis 客户端；V1 用于 RAG 缓存、RQ 队列和 Agent 临时状态。"""
    # 中文注释：懒加载 redis，保证基础应用导入不依赖完整运行时组件。
    from redis import Redis

    return Redis.from_url(settings.redis_url, decode_responses=True)
