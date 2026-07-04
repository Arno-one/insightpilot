from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_memory_policy_validation_blocks_context_packet_with_out_of_range_max_chars():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_memory_policy_block_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_memory_policy_block_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            draft = service.create_agent_definition(
                db,
                current_user,
                agent_code="memory_policy_block_agent",
                agent_name="记忆策略阻断Agent",
                description="用于验证记忆策略门禁",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={"entrypoint": "memory_policy_graph"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 50000},
            )

            validation = service.validate_agent_memory_policy(db, current_user, definition_id=draft["definition_id"])
            publish_result = service.publish_agent_definition(db, current_user, definition_id=draft["definition_id"])
            loaded = service.get_agent_definition(db, current_user, definition_id=draft["definition_id"])

        assert validation["valid"] is False
        assert validation["errors"][0]["code"] == "memory_max_chars_out_of_range"
        assert publish_result["published"] is False
        assert "memory_max_chars_out_of_range" in {item["code"] for item in publish_result["validation"]["errors"]}
        assert loaded["status"] == "draft"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)


def test_memory_policy_validation_keeps_empty_policy_as_warning():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_memory_policy_warning_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_memory_policy_warning_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            draft = service.create_agent_definition(
                db,
                current_user,
                agent_code="memory_policy_warning_agent",
                agent_name="默认记忆策略Agent",
                description="用于验证空记忆策略提示",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="draft",
                version=1,
                config_json={"entrypoint": "memory_policy_warning_graph"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )

            validation = service.validate_agent_memory_policy(db, current_user, definition_id=draft["definition_id"])

        # 中文注释：未启用记忆策略时仍可发布，只提醒后续 Runtime 不会注入上下文包。
        assert validation["valid"] is True
        assert validation["warnings"][0]["code"] == "memory_policy_empty"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
