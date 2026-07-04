from uuid import uuid4

from sqlalchemy import text

from app.core.database import ReadonlySessionLocal, SessionLocal
from app.modules.nl2sql import service
from tests.test_nl2sql_persistence_v1 import _cleanup_nl2sql_fixture, _ensure_nl2sql_tables_exist


def _ensure_probe_table_exists():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS nl2sql_probe (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  probe_id VARCHAR(64) NOT NULL,
                  label VARCHAR(120) NOT NULL,
                  is_deleted TINYINT NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  KEY idx_tenant_deleted (tenant_id, is_deleted)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _seed_probe_rows(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM nl2sql_probe WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(
            text(
                """
                INSERT INTO nl2sql_probe (tenant_id, probe_id, label, is_deleted)
                VALUES
                (:tenant_id, 'probe_visible', '可见数据', 0),
                (:tenant_id, 'probe_deleted', '已删除数据', 1)
                """
            ),
            {"tenant_id": tenant_id},
        )
        db.commit()


def _cleanup_probe_rows(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM nl2sql_probe WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_nl2sql_query_pipeline_injects_soft_delete_executes_and_uses_cache(monkeypatch):
    _ensure_nl2sql_tables_exist()
    _ensure_probe_table_exists()
    service._cache.clear()
    tenant_id = f"tenant_nl2sql_{uuid4().hex[:8]}"
    user_id = f"user_nl2sql_{uuid4().hex[:8]}"
    current_user = {"tenant_id": tenant_id, "user_id": user_id}
    _seed_probe_rows(tenant_id)

    monkeypatch.setattr(service, "build_schema_text", lambda: "nl2sql_probe(tenant_id, probe_id, label, is_deleted)")
    monkeypatch.setattr(service, "get_tables_with_column", lambda column_name: {"nl2sql_probe"})
    monkeypatch.setattr(
        service,
        "generate_sql",
        lambda question, schema_text=None: (
            "SELECT probe_id, label FROM nl2sql_probe WHERE tenant_id = :tenant_id ORDER BY probe_id",
            8,
        ),
    )

    try:
        with SessionLocal() as db_rw, ReadonlySessionLocal() as db_readonly:
            first = service.query(db_rw, db_readonly, current_user, question="列出测试数据")

        with SessionLocal() as db_rw, ReadonlySessionLocal() as db_readonly:
            second = service.query(db_rw, db_readonly, current_user, question="列出测试数据")

        assert first["is_cached"] is False
        assert "nl2sql_probe.is_deleted = 0" in first["sql"]
        assert first["result"]["row_count"] == 1
        assert first["result"]["rows"][0]["probe_id"] == "probe_visible"
        assert second["is_cached"] is True
        assert second["result"] == first["result"]
    finally:
        service._cache.clear()
        _cleanup_probe_rows(tenant_id)
        _cleanup_nl2sql_fixture(tenant_id)


def test_nl2sql_query_pipeline_persists_unsupported_without_external_llm(monkeypatch):
    _ensure_nl2sql_tables_exist()
    service._cache.clear()
    tenant_id = f"tenant_nl2sql_{uuid4().hex[:8]}"
    user_id = f"user_nl2sql_{uuid4().hex[:8]}"
    current_user = {"tenant_id": tenant_id, "user_id": user_id}

    monkeypatch.setattr(service.settings, "deepseek_api_key", "")
    monkeypatch.setattr(service, "build_schema_text", lambda: "empty schema")

    try:
        with SessionLocal() as db_rw, ReadonlySessionLocal() as db_readonly:
            result = service.query(db_rw, db_readonly, current_user, question="今天天气怎么样")
            detail = service.load_session_detail(db_rw, current_user, session_id=result["session_id"])

        assert result["is_cached"] is False
        assert result["error"] == "当前问题超出数据库问答范围"
        assert detail["session"]["last_query_status"] == "failed"
        assert detail["messages"][0]["content"] == "当前问题超出数据库问答范围"
    finally:
        service._cache.clear()
        _cleanup_nl2sql_fixture(tenant_id)
