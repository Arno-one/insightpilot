from app.modules.system import router as system_router
from app.shared import release_gate
from scripts import print_release_gate_checklist


def test_release_gate_allows_pilot_when_only_warnings_exist():
    checklist = release_gate.summarize_release_gate(tenant_id="demo_tenant")

    assert checklist["gate_version"] == "release_gate_checklist_v1"
    assert checklist["release_decision"] == "pilot_allowed"
    assert checklist["can_release_to_pilot"] is True
    assert checklist["can_release_to_production"] is False
    assert checklist["severity_counts"]["blocker"] == 0
    assert checklist["severity_counts"]["warning"] >= 1


def test_release_gate_blocks_production_when_deployment_has_blockers(monkeypatch):
    monkeypatch.setattr(
        release_gate,
        "summarize_deployment_readiness",
        lambda public=True: {
            "readiness_version": "deployment_readiness_v1",
            "overall_status": "blocked",
            "check_counts": {"pass": 1, "warn": 0, "fail": 2},
            "blocking_count": 2,
            "warning_count": 0,
        },
    )

    checklist = release_gate.summarize_release_gate()
    deployment_item = next(item for item in checklist["items"] if item["item_id"] == "deployment_blockers")

    assert checklist["release_decision"] == "production_blocked"
    assert checklist["can_release_to_pilot"] is False
    assert deployment_item["severity"] == "blocker"


def test_release_gate_keeps_external_actions_manual():
    checklist = release_gate.summarize_release_gate()
    boundary = checklist["execution_boundary"]
    external_item = next(item for item in checklist["items"] if item["item_id"] == "external_action_boundary")

    # 中文注释：真实外发、真实恢复、对象存储等动作必须保持人工确认，不允许门禁清单自动执行。
    assert boundary["checklist_only"] is True
    assert boundary["external_write_enabled"] is False
    assert boundary["auto_release_enabled"] is False
    assert external_item["severity"] == "warning"
    assert "external_action_boundary" in checklist["manual_confirmation_required"]


def test_system_release_gate_returns_protected_checklist(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_release_gate",
        lambda tenant_id=None: {
            "gate_version": "release_gate_checklist_v1",
            "release_decision": "pilot_allowed",
            "item_count": 2,
            "severity_counts": {"pass": 1, "warning": 1, "blocker": 0},
        },
    )

    response = system_router.get_release_gate(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"}
    )

    assert response["code"] == 200
    assert response["data"]["gate_version"] == "release_gate_checklist_v1"
    assert response["total"] == 2


def test_print_release_gate_checklist_script_exit_code(capsys):
    exit_code = print_release_gate_checklist.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"gate_version": "release_gate_checklist_v1"' in output
    assert '"auto_release_enabled": false' in output
