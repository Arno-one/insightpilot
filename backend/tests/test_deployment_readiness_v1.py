import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.modules.system import router as system_router
from app.shared import deployment_readiness
from scripts import verify_deployment_readiness


def _settings_with(**overrides) -> Settings:
    base = Settings(_env_file=None).model_copy(
        update={
            "app_env": "development",
            "app_port": 8088,
            "auth_secret_key": "secure-auth-secret-for-enterprise-vnext-76",
            "mysql_user": "insight_app",
            "mysql_password": "mysql-secret-76",
            "mysql_readonly_user": "insight_ro",
            "mysql_readonly_password": "mysql-readonly-secret-76",
            "redis_password": "redis-secret-76",
            "deepseek_api_key": "llm-secret-76",
            "smtp_host": "smtp.example.com",
            "sender_email": "noreply@example.com",
            "smtp_auth_code": "smtp-secret-76",
            "milvus_uri": "http://milvus.internal:19530",
            "embedding_dimension": 1024,
        }
    )
    return base.model_copy(update=overrides)


def test_deployment_readiness_reports_ready_without_secret_leakage():
    readiness = deployment_readiness.summarize_deployment_readiness(_settings_with(), public=False)
    dumped = json.dumps(readiness, ensure_ascii=False)

    assert readiness["readiness_version"] == "deployment_readiness_v1"
    assert readiness["overall_status"] == "ready"
    assert readiness["check_counts"]["fail"] == 0
    # 中文注释：体检结果只暴露配置状态，不能把任何密钥原文写进 API 或脚本输出。
    for secret in ["mysql-secret-76", "redis-secret-76", "llm-secret-76", "smtp-secret-76"]:
        assert secret not in dumped


def test_deployment_readiness_blocks_unsafe_production_defaults():
    readiness = deployment_readiness.summarize_deployment_readiness(
        _settings_with(
            app_env="production",
            auth_secret_key="change-me",
            mysql_password="",
            redis_password=None,
            smtp_host="smtp.example.com",
            sender_email="",
            smtp_auth_code="smtp-secret-76",
        ),
        public=False,
    )

    assert readiness["overall_status"] == "blocked"
    assert readiness["check_counts"]["fail"] >= 4
    failed_ids = {item["check_id"] for item in readiness["checks"] if item["status"] == "fail"}
    assert {
        "auth_secret_strength",
        "mysql_password_configured",
        "redis_password_configured",
        "smtp_config_complete",
    }.issubset(failed_ids)


def test_public_readiness_endpoint_uses_503_for_blocking_state(monkeypatch):
    monkeypatch.setattr(
        "app.main.summarize_deployment_readiness",
        lambda public=True: {
            "readiness_version": "deployment_readiness_v1",
            "overall_status": "blocked",
            "check_counts": {"pass": 1, "warn": 0, "fail": 1},
            "blocking_count": 1,
            "warning_count": 0,
        },
    )

    response = TestClient(app).get("/health/readiness")

    assert response.status_code == 503
    data = response.json()["data"]
    assert data["overall_status"] == "blocked"
    assert "checks" not in data
    assert "app" not in data


def test_system_deployment_readiness_returns_protected_detail(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_deployment_readiness",
        lambda public=False: {
            "readiness_version": "deployment_readiness_v1",
            "overall_status": "ready",
            "check_counts": {"pass": 2, "warn": 1, "fail": 0},
            "checks": [{"check_id": "demo", "status": "pass"}],
        },
    )

    response = system_router.get_deployment_readiness(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"}
    )

    assert response["code"] == 200
    assert response["data"]["overall_status"] == "ready"
    assert response["total"] == 3


def test_verify_deployment_readiness_script_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        verify_deployment_readiness,
        "summarize_deployment_readiness",
        lambda public=False: {
            "readiness_version": "deployment_readiness_v1",
            "overall_status": "blocked",
            "check_counts": {"pass": 0, "warn": 0, "fail": 1},
        },
    )

    exit_code = verify_deployment_readiness.main()

    assert exit_code == 1
    assert '"overall_status": "blocked"' in capsys.readouterr().out
