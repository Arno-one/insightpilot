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

    redis_host: str = Field("localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(6379, validation_alias="REDIS_PORT")
    redis_db: int = Field(0, validation_alias="REDIS_DB")
    redis_password: str | None = Field(None, validation_alias="REDIS_PASSWORD")

    auth_secret_key: str = Field("change-me", validation_alias="AUTH_SECRET_KEY")
    auth_token_expire_minutes: int = Field(720, validation_alias="AUTH_TOKEN_EXPIRE_MINUTES")
    auth_pbkdf2_iterations: int = Field(600000, validation_alias="AUTH_PBKDF2_ITERATIONS")

    deepseek_api_key: str = Field("", validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field("https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")

    dashscope_api_key: str = Field("", validation_alias="DASHSCOPE_API_KEY")
    aliyun_api_key: str = Field("", validation_alias="ALIYUN_API_KEY")

    milvus_uri: str = Field("http://localhost:19530", validation_alias="MILVUS_URI")
    milvus_db_name: str = Field("insightpilot_rag", validation_alias="MILVUS_DB_NAME")
    rag_document_collection: str = Field("insightpilot_document_chunks", validation_alias="RAG_DOCUMENT_COLLECTION")
    rag_qa_collection: str = Field("insightpilot_qa_pairs", validation_alias="RAG_QA_COLLECTION")

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
