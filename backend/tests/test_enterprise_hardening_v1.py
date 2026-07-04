from app.modules.system import router as system_router
from app.shared import enterprise_hardening
from scripts import print_enterprise_hardening_report


def test_enterprise_hardening_report_covers_phase_controls():
    report = enterprise_hardening.summarize_enterprise_hardening(tenant_id="demo_tenant")
    control_ids = {item["control_id"] for item in report["controls"]}

    assert report["hardening_version"] == "enterprise_hardening_v1"
    assert report["phase_range"] == "VNext-67..VNext-78"
    assert report["control_count"] == 11
    assert {
        "mcp_gateway_registry",
        "mcp_tool_permission",
        "mail_mcp_trace",
        "calendar_task_reservation",
        "tenant_boundary",
        "org_team_model",
        "audit_policy",
        "runtime_queue",
        "event_bus",
        "deployment_readiness",
        "backup_recovery",
    } == control_ids


def test_enterprise_hardening_report_is_readonly_and_payload_safe():
    report = enterprise_hardening.summarize_enterprise_hardening(tenant_id="demo_tenant")
    event_bus = next(item for item in report["controls"] if item["control_id"] == "event_bus")
    runtime_queue = next(item for item in report["controls"] if item["control_id"] == "runtime_queue")

    # 中文注释：阶段报告只暴露聚合计数，不输出事件 payload 或队列 payload，避免把运维总览变成数据泄漏面。
    assert report["execution_boundary"]["report_only"] is True
    assert report["execution_boundary"]["external_write_enabled"] is False
    assert "latest_events" not in event_bus["evidence"]
    assert "latest_items" not in runtime_queue["evidence"]


def test_enterprise_hardening_warns_when_sub_checks_have_warnings():
    report = enterprise_hardening.summarize_enterprise_hardening()

    assert report["overall_status"] in {"ready", "ready_with_warnings"}
    assert report["status_counts"]["blocked"] == 0
    if report["status_counts"]["warn"] > 0:
        assert report["overall_status"] == "ready_with_warnings"
        assert report["stage_gate"]["should_fix_before_production"]


def test_system_enterprise_hardening_returns_protected_report(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_enterprise_hardening",
        lambda tenant_id=None: {
            "hardening_version": "enterprise_hardening_v1",
            "phase_range": "VNext-67..VNext-78",
            "overall_status": "ready",
            "control_count": 3,
            "status_counts": {"ready": 3, "warn": 0, "blocked": 0},
        },
    )

    response = system_router.get_enterprise_hardening(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"}
    )

    assert response["code"] == 200
    assert response["data"]["hardening_version"] == "enterprise_hardening_v1"
    assert response["total"] == 3


def test_print_enterprise_hardening_report_script_exit_code(capsys):
    exit_code = print_enterprise_hardening_report.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"hardening_version": "enterprise_hardening_v1"' in output
    assert '"external_write_enabled": false' in output
