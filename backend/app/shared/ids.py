from uuid import uuid4


def new_id(prefix: str) -> str:
    """生成业务 ID，避免前端和日志直接依赖数据库自增 ID。"""
    return f"{prefix}_{uuid4().hex[:16]}"
