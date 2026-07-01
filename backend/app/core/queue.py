from app.core.redis import get_redis


def get_default_queue():
    """默认 RQ 队列，承载 RAG 入库、风险扫描和经营日报任务。"""
    # 中文注释：懒加载 RQ，避免未安装完整依赖时影响 FastAPI 基础应用导入。
    from rq import Queue

    return Queue("insightpilot-default", connection=get_redis())
