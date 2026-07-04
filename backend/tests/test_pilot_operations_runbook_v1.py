from app.modules.system import router as system_router
from app.shared import pilot_operations_runbook
from scripts import print_pilot_operations_runbook


def _acceptance_report(status: str = "accepted_with_warnings", blockers: list[dict] | None = None, warnings: list[dict] | None = None):
    blockers = blockers or []
    warnings = warnings or [
        {
            "source": "release_gate",
            "reason": "manual_confirmation_required",
            "items": ["external_action_boundary"],
        }
    ]
    return {
        "report_version": "pilot_acceptance_report_v1",
        "tenant_id": "demo_tenant",
        "overall_status": status,
        "acceptance_gate": {
            "can_enter_pilot": not blockers,
            "can_accept_pilot": not blockers,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "blockers": blockers,
            "warnings": warnings,
        },
        "deliverables": [
            {
                "deliverable_id": "system_health_console",
                "title": "系统健康控制台",
                "source": "/system/health",
                "status": "ready",
            }
        ],
    }


def _smoke_plan():
    return {
        "plan_version": "operational_smoke_test_plan_v1",
        "steps": [
            {"step_id": "auth_login", "priority": "p0"},
            {"step_id": "crm_customer_query", "priority": "p0"},
            {"step_id": "nl2sql_audit_read", "priority": "p1"},
        ],
    }


def test_pilot_operations_runbook_is_operable_with_acceptance_warnings(monkeypatch):
    monkeypatch.setattr(
        pilot_operations_runbook,
        "summarize_pilot_acceptance_report",
        lambda db, tenant_id: _acceptance_report(),
    )
    monkeypatch.setattr(pilot_operations_runbook, "summarize_smoke_test_plan", _smoke_plan)

    runbook = pilot_operations_runbook.summarize_pilot_operations_runbook(object(), tenant_id="demo_tenant")

    assert runbook["runbook_version"] == "pilot_operations_runbook_v1"
    assert runbook["overall_status"] == "ready_with_warnings"
    assert runbook["pilot_operable"] is True
    assert runbook["watch_item_count"] == 1
    assert runbook["cadences"][1]["steps"] == ["auth_login", "crm_customer_query"]


def test_pilot_operations_runbook_blocks_when_acceptance_blocks(monkeypatch):
    blocker = {
        "source": "pilot_data_pack",
        "reason": "pilot_data_incomplete",
        "items": ["business_reports"],
    }
    monkeypatch.setattr(
        pilot_operations_runbook,
        "summarize_pilot_acceptance_report",
        lambda db, tenant_id: _acceptance_report(status="blocked", blockers=[blocker], warnings=[]),
    )
    monkeypatch.setattr(pilot_operations_runbook, "summarize_smoke_test_plan", _smoke_plan)

    runbook = pilot_operations_runbook.summarize_pilot_operations_runbook(object(), tenant_id="demo_tenant")

    assert runbook["overall_status"] == "blocked"
    assert runbook["pilot_operable"] is False
    assert runbook["watch_items"][0]["severity"] == "blocker"


def test_pilot_operations_runbook_keeps_operator_boundaries_readonly(monkeypatch):
    monkeypatch.setattr(
        pilot_operations_runbook,
        "summarize_pilot_acceptance_report",
        lambda db, tenant_id: _acceptance_report(status="accepted", warnings=[]),
    )
    monkeypatch.setattr(pilot_operations_runbook, "summarize_smoke_test_plan", _smoke_plan)

    runbook = pilot_operations_runbook.summarize_pilot_operations_runbook(object(), tenant_id="demo_tenant")
    boundary = runbook["execution_boundary"]
    forbidden = {item["boundary_id"]: item for item in runbook["operator_boundaries"] if not item["allowed"]}

    # 中文注释：运营手册只能指导人工值守，不能越过暂停确认去执行外发、恢复或发布。
    assert boundary["readonly"] is True
    assert boundary["external_write_enabled"] is False
    assert boundary["auto_execute_enabled"] is False
    assert boundary["operator_record_persistence_enabled"] is False
    assert {"no_external_write", "no_destructive_recovery"}.issubset(forbidden)


def test_system_pilot_operations_runbook_returns_protected_runbook(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_pilot_operations_runbook",
        lambda db, tenant_id: {
            "runbook_version": "pilot_operations_runbook_v1",
            "overall_status": "ready_with_warnings",
            "cadence_count": 3,
        },
    )

    response = system_router.get_pilot_operations_runbook(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"},
        db=object(),
    )

    assert response["code"] == 200
    assert response["data"]["runbook_version"] == "pilot_operations_runbook_v1"
    assert response["total"] == 3


def test_print_pilot_operations_runbook_script_exit_code(monkeypatch, capsys):
    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(print_pilot_operations_runbook, "SessionLocal", _SessionFactory())
    monkeypatch.setattr(
        print_pilot_operations_runbook,
        "summarize_pilot_operations_runbook",
        lambda db, tenant_id: {
            "runbook_version": "pilot_operations_runbook_v1",
            "pilot_operable": True,
            "execution_boundary": {"auto_execute_enabled": False},
        },
    )

    exit_code = print_pilot_operations_runbook.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"runbook_version": "pilot_operations_runbook_v1"' in output
    assert '"auto_execute_enabled": false' in output
