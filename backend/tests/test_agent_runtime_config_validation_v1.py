from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_runtime_config_validation_blocks_workflow_without_entrypoint_on_publish():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_runtime_config_block_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_runtime_config_block_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            draft = service.create_agent_definition(
                db,
                current_user,
                agent_code="runtime_config_block_agent",
                agent_name="运行时配置阻断Agent",
                description="用于验证 workflow entrypoint 门禁",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )

            validation = service.validate_agent_runtime_config(db, current_user, definition_id=draft["definition_id"])
            publish_result = service.publish_agent_definition(db, current_user, definition_id=draft["definition_id"])
            loaded = service.get_agent_definition(db, current_user, definition_id=draft["definition_id"])

        assert validation["valid"] is False
        assert validation["errors"][0]["code"] == "runtime_entrypoint_missing"
        assert publish_result["published"] is False
        assert "runtime_entrypoint_missing" in {item["code"] for item in publish_result["validation"]["errors"]}
        assert loaded["status"] == "draft"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)


def test_runtime_config_validation_allows_chat_without_entrypoint_as_warning():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_runtime_config_chat_warning_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_runtime_config_chat_warning_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            draft = service.create_agent_definition(
                db,
                current_user,
                agent_code="runtime_config_chat_agent",
                agent_name="默认对话Runtime Agent",
                description="用于验证 chat 默认入口提示",
                agent_type="chat",
                runtime_type="chat",
                status="draft",
                version=1,
                config_json={},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )

            validation = service.validate_agent_runtime_config(db, current_user, definition_id=draft["definition_id"])

        # 中文注释：chat 类型可以交给默认对话 Runtime，缺 entrypoint 只提示，不阻断。
        assert validation["valid"] is True
        assert validation["warnings"][0]["code"] == "chat_entrypoint_empty"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
