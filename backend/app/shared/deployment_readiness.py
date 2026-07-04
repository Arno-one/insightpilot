from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.core.config import Settings, settings

ReadinessStatus = Literal["pass", "warn", "fail"]

DEPLOYMENT_READINESS_VERSION = "deployment_readiness_v1"
PRODUCTION_ENVS = {"prod", "production"}
DEFAULT_SECRET_VALUES = {"", "change-me", "changeme", "please-change-me"}


@dataclass(frozen=True, slots=True)
class DeploymentReadinessCheck:
    """中文注释：单条部署体检结果只描述风险，不输出连接串、密码、Token 等敏感值。"""

    check_id: str
    component: str
    status: ReadinessStatus
    message: str
    recommendation: str

    def model_dump(self) -> dict:
        return asdict(self)


def _is_blank(value: str | None) -> bool:
    return not str(value or "").strip()


def _status_counts(checks: list[DeploymentReadinessCheck]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        counts[check.status] += 1
    return counts


def _add_check(
    checks: list[DeploymentReadinessCheck],
    *,
    check_id: str,
    component: str,
    status: ReadinessStatus,
    message: str,
    recommendation: str,
) -> None:
    checks.append(
        DeploymentReadinessCheck(
            check_id=check_id,
            component=component,
            status=status,
            message=message,
            recommendation=recommendation,
        )
    )


def _build_checks(config: Settings) -> list[DeploymentReadinessCheck]:
    checks: list[DeploymentReadinessCheck] = []
    app_env = config.app_env.lower()
    is_production = app_env in PRODUCTION_ENVS

    _add_check(
        checks,
        check_id="app_port_valid",
        component="app",
        status="pass" if 1 <= config.app_port <= 65535 else "fail",
        message="应用端口在合法范围内" if 1 <= config.app_port <= 65535 else "应用端口不在 1-65535 范围内",
        recommendation="保持 APP_PORT 为容器或进程实际监听端口。",
    )

    secret_normalized = config.auth_secret_key.strip().lower()
    auth_secret_weak = secret_normalized in DEFAULT_SECRET_VALUES or len(config.auth_secret_key.strip()) < 32
    _add_check(
        checks,
        check_id="auth_secret_strength",
        component="auth",
        status="fail" if is_production and auth_secret_weak else "warn" if auth_secret_weak else "pass",
        message="生产环境认证密钥过弱" if is_production and auth_secret_weak else "认证密钥已配置",
        recommendation="生产环境必须配置至少 32 位的 AUTH_SECRET_KEY，且不能使用默认值。",
    )

    mysql_password_missing = _is_blank(config.mysql_password)
    _add_check(
        checks,
        check_id="mysql_password_configured",
        component="database",
        status="fail" if is_production and mysql_password_missing else "warn" if mysql_password_missing else "pass",
        message="数据库密码未配置" if mysql_password_missing else "数据库密码已配置",
        recommendation="生产环境必须通过 MYSQL_PASSWORD/DB_PASSWORD 注入强密码。",
    )

    mysql_uses_root = config.mysql_user.strip().lower() == "root"
    _add_check(
        checks,
        check_id="mysql_least_privilege_user",
        component="database",
        status="warn" if mysql_uses_root else "pass",
        message="数据库使用 root 账号" if mysql_uses_root else "数据库账号不是 root",
        recommendation="生产环境建议使用最小权限业务账号，避免使用 root 直连应用。",
    )

    readonly_isolated = bool(config.mysql_readonly_user and config.mysql_readonly_user != config.mysql_user)
    _add_check(
        checks,
        check_id="mysql_readonly_identity",
        component="database",
        status="pass" if readonly_isolated else "warn",
        message="只读库账号已独立配置" if readonly_isolated else "只读库账号复用主库账号",
        recommendation="上线前为只读查询配置 MYSQL_READONLY_USER/MYSQL_READONLY_PASSWORD，降低误写风险。",
    )

    redis_password_missing = _is_blank(config.redis_password)
    _add_check(
        checks,
        check_id="redis_password_configured",
        component="redis",
        status="fail" if is_production and redis_password_missing else "warn" if redis_password_missing else "pass",
        message="Redis 密码未配置" if redis_password_missing else "Redis 密码已配置",
        recommendation="生产环境必须通过 REDIS_PASSWORD 注入密码，并限制网络访问范围。",
    )

    llm_configured = not _is_blank(config.deepseek_api_key)
    _add_check(
        checks,
        check_id="llm_key_configured",
        component="llm",
        status="pass" if llm_configured else "warn",
        message="LLM API Key 已配置" if llm_configured else "LLM API Key 未配置",
        recommendation="需要 NL2SQL、Agent 推理能力时，配置 DEEPSEEK_API_KEY 或接入等价模型网关。",
    )

    smtp_fields = [config.smtp_host, config.sender_email, config.smtp_auth_code]
    smtp_configured_count = sum(0 if _is_blank(value) else 1 for value in smtp_fields)
    smtp_status: ReadinessStatus = "pass"
    if smtp_configured_count == 0:
        smtp_status = "warn"
    elif smtp_configured_count != len(smtp_fields):
        smtp_status = "fail" if is_production else "warn"
    _add_check(
        checks,
        check_id="smtp_config_complete",
        component="notification",
        status=smtp_status,
        message="SMTP 配置完整" if smtp_status == "pass" else "SMTP 配置未完整",
        recommendation="邮件投递需要同时配置 SMTP_HOST、SENDER_EMAIL、SMTP_AUTH_CODE。",
    )

    rag_vector_configured = not _is_blank(config.milvus_uri) and config.embedding_dimension > 0
    _add_check(
        checks,
        check_id="rag_vector_configured",
        component="rag",
        status="pass" if rag_vector_configured else "warn",
        message="向量库基础配置已就绪" if rag_vector_configured else "向量库基础配置不完整",
        recommendation="RAG 能力需要 MILVUS_URI 与 EMBEDDING_DIMENSION 保持有效。",
    )

    return checks


def summarize_deployment_readiness(config: Settings | None = None, *, public: bool = False) -> dict:
    """中文注释：输出部署就绪摘要；public=True 时只给探针安全字段，避免泄漏内部配置细节。"""

    config = config or settings
    checks = _build_checks(config)
    counts = _status_counts(checks)
    overall_status = "blocked" if counts["fail"] else "ready"

    summary = {
        "readiness_version": DEPLOYMENT_READINESS_VERSION,
        "overall_status": overall_status,
        "check_counts": counts,
        "blocking_count": counts["fail"],
        "warning_count": counts["warn"],
    }
    if public:
        return summary

    return {
        **summary,
        "app": {
            "app_name": config.app_name,
            "app_env": config.app_env,
            "app_host": config.app_host,
            "app_port": config.app_port,
        },
        "capabilities": {
            "database_configured": not _is_blank(config.mysql_host) and not _is_blank(config.mysql_database),
            "readonly_database_configured": bool(config.mysql_readonly_user),
            "redis_configured": not _is_blank(config.redis_host),
            "auth_secret_configured": config.auth_secret_key.strip().lower() not in DEFAULT_SECRET_VALUES,
            "llm_configured": not _is_blank(config.deepseek_api_key),
            "smtp_configured": all(
                not _is_blank(value) for value in (config.smtp_host, config.sender_email, config.smtp_auth_code)
            ),
            "rag_vector_configured": not _is_blank(config.milvus_uri) and config.embedding_dimension > 0,
        },
        "checks": [check.model_dump() for check in checks],
        "external_connectivity": {
            "mode": "not_checked",
            "reason": "V1 只做配置与启动前风险收口，不主动连接外部数据库、Redis、SMTP 或模型服务。",
        },
    }
