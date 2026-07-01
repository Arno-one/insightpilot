from rq import Worker

from app.core.queue import get_default_queue


if __name__ == "__main__":
    queue = get_default_queue()
    # 中文注释：启动轻量 RQ Worker，处理 RAG 入库、风险扫描和经营日报生成任务。
    Worker([queue]).work()
