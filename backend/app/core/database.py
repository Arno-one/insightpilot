from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 模型基类，所有业务表都从这里继承。"""


engine = create_engine(
    settings.mysql_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)

readonly_engine = create_engine(
    settings.mysql_readonly_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    isolation_level="READ COMMITTED",
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
ReadonlySessionLocal = sessionmaker(bind=readonly_engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 数据库依赖，保证每次请求结束后关闭连接。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_readonly_db() -> Generator[Session, None, None]:
    """NL2SQL 专用只读连接依赖；生产环境建议配置独立只读账号。"""
    db = ReadonlySessionLocal()
    try:
        yield db
    finally:
        db.close()
