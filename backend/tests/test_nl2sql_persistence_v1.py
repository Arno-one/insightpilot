from uuid import uuid4

from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.nl2sql import dao, service


def _ensure_nl2sql_tables_exist():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS nl2sql_session (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  session_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  title VARCHAR(120) NOT NULL DEFAULT '数据问答会话',
                  status VARCHAR(30) NOT NULL DEFAULT 'active',
                  data_scope VARCHAR(30) NOT NULL DEFAULT 'self',
                  context_json JSON NULL,
                  last_question TEXT NULL,
                  last_query_status VARCHAR(30) NULL,
                  message_count INT NOT NULL DEFAULT 0,
                  last_message_at DATETIME NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_session_id (session_id),
                  KEY idx_tenant_user_updated (tenant_id, user_id, updated_at),
                  KEY idx_tenant_status_updated (tenant_id, status, updated_at),
                  KEY idx_tenant_scope_updated (tenant_id, data_scope, updated_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS nl2sql_message (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  message_id VARCHAR(64) NOT NULL,
                  session_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  role VARCHAR(30) NOT NULL,
                  content TEXT NOT NULL,
                  query_id VARCHAR(64) NULL,
                  question TEXT NULL,
                  generated_sql TEXT NULL,
                  result_json JSON NULL,
                  cost_ms INT NOT NULL DEFAULT 0,
                  is_cached TINYINT NOT NULL DEFAULT 0,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_message_id (message_id),
                  KEY idx_tenant_session_created (tenant_id, session_id, created_at),
                  KEY idx_tenant_user_created (tenant_id, user_id, created_at),
                  KEY idx_tenant_query (tenant_id, query_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS nl2sql_query_audit (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  query_id VARCHAR(64) NOT NULL,
                  session_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  question TEXT NOT NULL,
                  generated_sql TEXT NULL,
                  normalized_sql TEXT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'created',
                  validator_result_json JSON NULL,
                  execution_summary_json JSON NULL,
                  row_count INT NULL,
                  error_message TEXT NULL,
                  elapsed_ms INT NOT NULL DEFAULT 0,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  finished_at DATETIME NULL,
                  UNIQUE KEY uk_query_id (query_id),
                  KEY idx_tenant_session_created (tenant_id, session_id, created_at),
                  KEY idx_tenant_user_created (tenant_id, user_id, created_at),
                  KEY idx_tenant_status_created (tenant_id, status, created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _cleanup_nl2sql_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM nl2sql_message WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM nl2sql_query_audit WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.execute(text("DELETE FROM nl2sql_session WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_nl2sql_session_message_and_audit_are_persisted():
    _ensure_nl2sql_tables_exist()
    tenant_id = f"tenant_nl2sql_{uuid4().hex[:8]}"
    user_id = f"user_nl2sql_{uuid4().hex[:8]}"
    current_user = {"tenant_id": tenant_id, "user_id": user_id}

    try:
        with SessionLocal() as db:
            session = service.create_session(
                db,
                current_user,
                title="本月客户统计",
                data_scope="self",
                context_json={"source": "test"},
            )
            message = service.append_message(
                db,
                current_user,
                session_id=session["session_id"],
                role="user",
                content="统计本月客户数量",
            )
            audit = service.create_query_audit(
                db,
                current_user,
                session_id=session["session_id"],
                question="统计本月客户数量",
            )
            updated = dao.update_query_audit(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                query_id=audit["query_id"],
                generated_sql="SELECT COUNT(*) FROM crm_customer WHERE tenant_id = :tenant_id",
                normalized_sql="SELECT COUNT(*) FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 100",
                status="executed",
                validator_result_json={"valid": True},
                execution_summary_json={"row_count": 1},
                row_count=1,
                elapsed_ms=3,
            )
            detail = service.load_session_detail(db, current_user, session_id=session["session_id"])

            assert session["session_id"].startswith("nl2sql_sess_")
            assert session["context_json"]["source"] == "test"
            assert message["message_id"].startswith("nl2sql_msg_")
            assert updated["status"] == "executed"
            assert updated["execution_summary_json"]["row_count"] == 1
            assert detail["session"]["message_count"] == 1
            assert detail["session"]["last_query_status"] == "executed"
            assert detail["messages"][0]["content"] == "统计本月客户数量"
    finally:
        _cleanup_nl2sql_fixture(tenant_id)
