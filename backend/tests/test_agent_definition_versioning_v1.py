from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_definition_can_clone_publish_and_load_latest_active_version():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_definition_versioning_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_definition_versioning_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            first = service.create_agent_definition(
                db,
                current_user,
                agent_code="sales_advisor",
                agent_name="销售顾问Agent",
                description="负责销售跟进建议",
                agent_type="sales",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "sales_advisor_graph"},
                tool_policy_json={"allowed_tools": ["crm.search_customers"]},
                memory_policy_json={"context_packet": True},
            )

            draft = service.clone_agent_definition(
                db,
                current_user,
                definition_id=first["definition_id"],
                agent_name="销售顾问Agent v2",
                config_json={"entrypoint": "sales_advisor_graph_v2"},
            )
            latest_before_publish = service.get_latest_active_agent_definition(
                db,
                current_user,
                agent_code="sales_advisor",
            )

            published = service.update_agent_definition_status(
                db,
                current_user,
                definition_id=draft["definition_id"],
                status="active",
            )
            first_after_publish = service.get_agent_definition(db, current_user, definition_id=first["definition_id"])
            latest_after_publish = service.get_latest_active_agent_definition(
                db,
                current_user,
                agent_code="sales_advisor",
            )

        assert draft["version"] == 2
        assert draft["status"] == "draft"
        assert draft["agent_name"] == "销售顾问Agent v2"
        assert draft["config_json"]["entrypoint"] == "sales_advisor_graph_v2"
        assert draft["tool_policy_json"] == first["tool_policy_json"]
        assert latest_before_publish["definition_id"] == first["definition_id"]

        # 中文注释：发布新版本后旧 active 自动禁用，运行时按 code 查询不会拿到两个候选版本。
        assert published["status"] == "active"
        assert first_after_publish["status"] == "disabled"
        assert latest_after_publish["definition_id"] == draft["definition_id"]
        assert latest_after_publish["version"] == 2
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
