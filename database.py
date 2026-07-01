"""数据库兼容入口。

新项目的真实数据库能力位于 `backend/app/core/database.py`。
保留根目录入口是为了兼容临时脚本或旧习惯，避免出现两套数据库连接配置。
"""
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import Base, SessionLocal, engine, get_db  # noqa: E402


Session = SessionLocal


def init_db() -> None:
    """根据 SQLAlchemy metadata 建表；V1 推荐优先使用 scripts/init_schema.sql。"""
    Base.metadata.create_all(bind=engine)
