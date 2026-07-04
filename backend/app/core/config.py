from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """统一配置入口，所有敏感信息从 .env 读取。"""

    model_config = SettingsConfigDict(
        env_file=(
            _PROJECT_ROOT / ".env",
            _BACKEND_DIR / ".env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "InsightPilot"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8088

    # 中文注释：兼容旧项目的 DB_* 环境变量，也支持新项目推荐的 MYSQL_*。
    mysql_host: str = Field("localhost", validation_alias=AliasChoices("MYSQL_HOST", "DB_HOST"))
    mysql_port: int = Field(3306, validation_alias=AliasChoices("MYSQL_PORT", "DB_PORT"))
    mysql_user: str = Field("root", validation_alias=AliasChoices("MYSQL_USER", "DB_USER"))
    mysql_password: str = Field("", validation_alias=AliasChoices("MYSQL_PASSWORD", "DB_PASSWORD"))
    mysql_database: str = Field("insightpilot", validation_alias=AliasChoices("MYSQL_DATABASE", "DB_NAME"))
    mysql_readonly_user: str | None = Field(None, validation_alias="MYSQL_READONLY_USER")
    mysql_readonly_password: str | None = Field(None, validation_alias="MYSQL_READONLY_PASSWORD")

    redis_host: str = Field("localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(6379, validation_alias="REDIS_PORT")
    redis_db: int = Field(0, validation_alias="REDIS_DB")
    redis_password: str | None = Field(None, validation_alias="REDIS_PASSWORD")

    auth_secret_key: str = Field("change-me", validation_alias="AUTH_SECRET_KEY")
    auth_token_expire_minutes: int = Field(720, validation_alias="AUTH_TOKEN_EXPIRE_MINUTES")
    auth_pbkdf2_iterations: int = Field(600000, validation_alias="AUTH_PBKDF2_ITERATIONS")

    deepseek_api_key: str = Field("", validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field("https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")
    nl2sql_model: str = Field("deepseek-chat", validation_alias="NL2SQL_MODEL")

    dashscope_api_key: str = Field("", validation_alias="DASHSCOPE_API_KEY")
    aliyun_api_key: str = Field("", validation_alias="ALIYUN_API_KEY")

    # 中文注释：邮件通道先基于 SMTP 打通，后续企业微信、飞书等可继续挂到统一 Gateway。
    smtp_host: str = Field("", validation_alias="SMTP_HOST")
    smtp_port: int = Field(465, validation_alias="SMTP_PORT")
    sender_email: str = Field("", validation_alias="SENDER_EMAIL")
    smtp_auth_code: str = Field("", validation_alias="SMTP_AUTH_CODE")
    smtp_sender_name: str = Field("InsightPilot", validation_alias="SMTP_SENDER_NAME")
    smtp_use_tls: bool = Field(True, validation_alias="SMTP_USE_TLS")
    smtp_use_ssl: bool | None = Field(None, validation_alias="SMTP_USE_SSL")
    smtp_timeout_seconds: int = Field(15, validation_alias="SMTP_TIMEOUT_SECONDS")

    milvus_uri: str = Field("http://localhost:19530", validation_alias="MILVUS_URI")
    milvus_db_name: str = Field("insightpilot_rag", validation_alias="MILVUS_DB_NAME")
    rag_document_collection: str = Field("insightpilot_document_chunks", validation_alias="RAG_DOCUMENT_COLLECTION")
    rag_qa_collection: str = Field("insightpilot_qa_pairs", validation_alias="RAG_QA_COLLECTION")
    rag_docs_dir: str = Field("docs/insightpilot_rag_docs", validation_alias="RAG_DOCS_DIR")
    embedding_dimension: int = Field(1024, validation_alias="EMBEDDING_DIMENSION")
    use_real_embedding: bool = Field(True, validation_alias="USE_REAL_EMBEDDING")
    rag_chunk_size: int = Field(500, validation_alias="RAG_CHUNK_SIZE")
    rag_chunk_overlap: int = Field(50, validation_alias="RAG_CHUNK_OVERLAP")

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def mysql_readonly_url(self) -> str:
        user = self.mysql_readonly_user or self.mysql_user
        password = self.mysql_readonly_password if self.mysql_readonly_password is not None else self.mysql_password
        return f"mysql+pymysql://{user}:{password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
