from app.core.database import SessionLocal
from app.modules.agent_studio import service
from test_agent_definition_v1 import _cleanup_agent_definition_fixture, _ensure_agent_definition_table_exists


def test_agent_studio_phase_regression_covers_definition_publish_audit_rollback_diff_and_overview():
    _ensure_agent_definition_table_exists()
    tenant_id = "tenant_agent_studio_phase_regression_v1"
    current_user = {
        "tenant_id": tenant_id,
        "user_id": "user_agent_studio_phase_regression_v1",
        "permission_codes": ["crm:customer:read:self"],
    }
    _cleanup_agent_definition_fixture(tenant_id)

    try:
        with SessionLocal() as db:
            first = service.create_agent_definition(
                db,
                current_user,
                agent_code="phase_regression_agent",
                agent_name="阶段回归Agent v1",
                description="阶段回归第一版",
                agent_type="quality_gate",
                runtime_type="workflow",
                status="active",
                version=1,
                config_json={"entrypoint": "phase_regression_graph_v1", "temperature": 0.1},
                tool_policy_json={"allowed_tools": ["data.query_sql"]},
                memory_policy_json={"context_packet": True, "max_chars": 1200},
            )
            second = service.clone_agent_definition(
                db,
                current_user,
                definition_id=first["definition_id"],
                agent_name="阶段回归Agent v2",
                description="阶段回归第二版",
                config_json={"entrypoint": "phase_regression_graph_v2", "temperature": 0.2},
                tool_policy_json={"allowed_tools": ["data.query_sql", "data.analyze_business"]},
                memory_policy_json={"context_packet": True, "max_chars": 2400},
            )

            publish_result = service.publish_agent_definition(db, current_user, definition_id=second["definition_id"])
            diff = service.diff_agent_definitions(
                db,
                current_user,
                base_definition_id=first["definition_id"],
                target_definition_id=second["definition_id"],
            )
            rollback_result = service.rollback_agent_definition(db, current_user, definition_id=first["definition_id"])
            latest_active = service.get_latest_active_agent_definition(
                db,
                current_user,
                agent_code="phase_regression_agent",
            )
            audits = service.list_agent_publish_audits(db, current_user, agent_code="phase_regression_agent")
            overview = service.summarize_agent_studio(db, current_user)

        assert publish_result["published"] is True
        assert rollback_result["rolled_back"] is True
        assert latest_active["definition_id"] == first["definition_id"]
        assert diff["summary"]["changed"] is True
        assert "config_json.entrypoint" in diff["changed_paths"]
        assert len(audits) == 2
        assert {item["message"] for item in audits} == {"Agent Definition 已发布", "Agent Definition 已回滚发布"}
        assert overview["definition_summary"]["total_count"] == 2
        assert overview["definition_summary"]["active_count"] == 1
        assert overview["definition_summary"]["disabled_count"] == 1
        assert overview["publish_audit_summary"]["published_count"] == 2
        # 中文注释：这条阶段回归把 VNext-55~65 的核心能力串起来，后续改动必须守住这条主链路。
        assert overview["active_definitions"][0]["definition_id"] == first["definition_id"]
    finally:
        _cleanup_agent_definition_fixture(tenant_id)
