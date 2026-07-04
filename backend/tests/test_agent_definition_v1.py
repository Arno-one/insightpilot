from sqlalchemy import text

from app.core.database import SessionLocal
from app.modules.agent_studio import service


def _ensure_agent_definition_table_exists():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_definition (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  definition_id VARCHAR(64) NOT NULL,
                  agent_code VARCHAR(80) NOT NULL,
                  agent_name VARCHAR(120) NOT NULL,
                  description TEXT NULL,
                  agent_type VARCHAR(50) NOT NULL DEFAULT 'custom',
                  runtime_type VARCHAR(50) NOT NULL DEFAULT 'chat',
                  status VARCHAR(30) NOT NULL DEFAULT 'draft',
                  version INT NOT NULL DEFAULT 1,
                  config_json JSON NULL,
                  tool_policy_json JSON NULL,
                  memory_policy_json JSON NULL,
                  created_by_user_id VARCHAR(64) NOT NULL,
                  updated_by_user_id VARCHAR(64) NOT NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_definition_id (definition_id),
                  UNIQUE KEY uk_tenant_agent_version (tenant_id, agent_code, version),
                  KEY idx_tenant_status_updated (tenant_id, status, updated_at),
                  KEY idx_tenant_agent_code (tenant_id, agent_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def _cleanup_agent_definition_fixture(tenant_id: str):
    with SessionLocal() as db:
        db.execute(text("DELETE FROM agent_definition WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
        db.commit()


def test_agent_definition_model_can_create_list_and_load_definition():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_definition_v1"
    user_id = "user_agent_definition_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            created = service.create_agent_definition(
                db,
                current_user,
                agent_code="customer_risk_advisor",
                agent_name="客户风险参谋",
                description="围绕客户风险、记忆和知识引用生成建议",
                agent_type="risk",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "risk_analysis_graph"},
                tool_policy_json={"allowed_tools": ["crm.get_customer_detail", "rag.retrieve_sales_context"]},
                memory_policy_json={"context_packet": True, "max_chars": 2400},
            )
            items = service.list_agent_definitions(db, current_user, status="active")
            loaded = service.get_agent_definition(db, current_user, definition_id=created["definition_id"])

        assert created["agent_code"] == "customer_risk_advisor"
        assert created["runtime_type"] == "workflow"
        assert created["config_json"]["entrypoint"] == "risk_analysis_graph"
        assert created["tool_policy_json"]["allowed_tools"] == ["crm.get_customer_detail", "rag.retrieve_sales_context"]
        assert created["memory_policy_json"]["context_packet"] is True
        assert len(items) == 1
        assert items[0]["definition_id"] == created["definition_id"]
        assert loaded["agent_name"] == "客户风险参谋"
        assert loaded["created_by_user_id"] == user_id
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
