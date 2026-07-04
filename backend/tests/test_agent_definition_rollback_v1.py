from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_definition_rollback_republishes_previous_version_and_writes_audit():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_definition_rollback_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_definition_rollback_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            first = service.create_agent_definition(
                db,
                current_user,
                agent_code="rollback_agent",
                agent_name="可回滚Agent v1",
                description="用于验证历史版本回滚",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "rollback_graph_v1"},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 1200},
            )
            second = service.clone_agent_definition(
                db,
                current_user,
                definition_id=first["definition_id"],
                agent_name="可回滚Agent v2",
                config_json={"entrypoint": "rollback_graph_v2"},
            )
            published_second = service.publish_agent_definition(db, current_user, definition_id=second["definition_id"])

            rollback_result = service.rollback_agent_definition(db, current_user, definition_id=first["definition_id"])
            first_after_rollback = service.get_agent_definition(db, current_user, definition_id=first["definition_id"])
            second_after_rollback = service.get_agent_definition(db, current_user, definition_id=second["definition_id"])
            audits = service.list_agent_publish_audits(db, current_user, definition_id=first["definition_id"])

        assert published_second["published"] is True
        assert rollback_result["rolled_back"] is True
        assert rollback_result["publish_audit"]["publish_status"] == "published"
        assert rollback_result["publish_audit"]["message"] == "Agent Definition 已回滚发布"
        assert first_after_rollback["status"] == "active"
        assert second_after_rollback["status"] == "disabled"
        assert audits[0]["audit_id"] == rollback_result["publish_audit"]["audit_id"]
        assert audits[0]["validation_json"]["valid"] is True
    finally:
        _cleanup_agent_definition_fixture(tenant_id)


def test_agent_definition_rollback_is_blocked_by_publish_gate_for_invalid_version():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_definition_rollback_block_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_definition_rollback_block_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            invalid = service.create_agent_definition(
                db,
                current_user,
                agent_code="rollback_block_agent",
                agent_name="不可回滚Agent",
                description="用于验证回滚门禁阻断",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="disabled",
                version=1,
                config_json={},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={},
            )

            rollback_result = service.rollback_agent_definition(db, current_user, definition_id=invalid["definition_id"])
            loaded = service.get_agent_definition(db, current_user, definition_id=invalid["definition_id"])

        # 中文注释：历史版本配置不合法时不能绕过发布门禁直接回滚上线。
        assert rollback_result["rolled_back"] is False
        assert rollback_result["publish_audit"]["publish_status"] == "blocked"
        assert "runtime_entrypoint_missing" in {item["code"] for item in rollback_result["validation"]["errors"]}
        assert loaded["status"] == "disabled"
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
