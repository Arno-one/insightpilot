from app.modules.system import router as system_router
from app.shared import pilot_acceptance_report
from scripts import print_pilot_acceptance_report


def _hardening(status: str = "ready", blockers: list[str] | None = None, warnings: list[str] | None = None):
    blockers = blockers or []
    warnings = warnings or []
    return {
        "hardening_version": "enterprise_hardening_v1",
        "overall_status": status,
        "control_count": 11,
        "status_counts": {
            "ready": 11 - len(blockers) - len(warnings),
            "warn": len(warnings),
            "blocked": len(blockers),
        },
        "stage_gate": {
            "can_enter_enterprise_pilot": not blockers,
            "must_fix_before_production": blockers,
            "should_fix_before_production": warnings,
        },
    }


def _release(can_pilot: bool = True, warnings: list[str] | None = None, blockers: list[str] | None = None):
    warnings = warnings or []
    blockers = blockers or []
    return {
        "gate_version": "release_gate_checklist_v1",
        "release_decision": "pilot_allowed" if can_pilot else "production_blocked",
        "can_release_to_pilot": can_pilot,
        "can_release_to_production": can_pilot and not warnings,
        "item_count": len(warnings) + len(blockers),
        "severity_counts": {"pass": 1, "warning": len(warnings), "blocker": len(blockers)},
        "manual_confirmation_required": [*warnings, *blockers],
        "items": [
            {
                "item_id": item_id,
                "severity": "warning",
            }
            for item_id in warnings
        ]
        + [
            {
                "item_id": item_id,
                "severity": "blocker",
            }
            for item_id in blockers
        ],
    }


def _smoke(status: str = "ready"):
    return {
        "plan_version": "operational_smoke_test_plan_v1",
        "overall_status": status,
        "step_count": 8,
        "priority_counts": {"p0": 4, "p1": 4, "p2": 0},
    }


def _pilot_data(status: str = "ready", missing: list[str] | None = None):
    missing = missing or []
    return {
        "pack_version": "enterprise_pilot_data_pack_v1",
        "overall_status": status,
        "check_count": 9,
        "status_counts": {"pass": 9 - len(missing), "fail": len(missing)},
        "missing_checks": missing,
    }


def _patch_dependencies(monkeypatch, *, hardening=None, release=None, smoke=None, pilot_data=None):
    monkeypatch.setattr(
        pilot_acceptance_report,
        "summarize_enterprise_hardening",
        lambda tenant_id=None: hardening or _hardening(),
    )
    monkeypatch.setattr(
        pilot_acceptance_report,
        "summarize_release_gate",
        lambda tenant_id=None: release or _release(warnings=["external_action_boundary"]),
    )
    monkeypatch.setattr(
        pilot_acceptance_report,
        "summarize_smoke_test_plan",
        lambda: smoke or _smoke(),
    )
    monkeypatch.setattr(
        pilot_acceptance_report,
        "summarize_pilot_data_pack",
        lambda db, tenant_id: pilot_data or _pilot_data(),
    )


def test_pilot_acceptance_report_accepts_ready_pack_with_warnings(monkeypatch):
    _patch_dependencies(monkeypatch)

    report = pilot_acceptance_report.summarize_pilot_acceptance_report(object(), tenant_id="demo_tenant")

    assert report["report_version"] == "pilot_acceptance_report_v1"
    assert report["overall_status"] == "accepted_with_warnings"
    assert report["acceptance_gate"]["can_enter_pilot"] is True
    assert report["acceptance_gate"]["can_accept_pilot"] is True
    assert report["acceptance_gate"]["blockers"] == []
    assert report["acceptance_gate"]["warnings"][0]["source"] == "release_gate"


def test_pilot_acceptance_report_blocks_when_release_gate_blocks(monkeypatch):
    _patch_dependencies(
        monkeypatch,
        release=_release(can_pilot=False, blockers=["deployment_blockers"]),
    )

    report = pilot_acceptance_report.summarize_pilot_acceptance_report(object(), tenant_id="demo_tenant")

    assert report["overall_status"] == "blocked"
    assert report["acceptance_gate"]["can_enter_pilot"] is False
    assert report["acceptance_gate"]["can_accept_pilot"] is False
    assert report["acceptance_gate"]["blockers"][0]["source"] == "release_gate"


def test_pilot_acceptance_report_blocks_when_pilot_data_incomplete(monkeypatch):
    _patch_dependencies(
        monkeypatch,
        pilot_data=_pilot_data(status="incomplete", missing=["business_reports"]),
    )

    report = pilot_acceptance_report.summarize_pilot_acceptance_report(object(), tenant_id="demo_tenant")

    assert report["overall_status"] == "blocked"
    assert report["sections"]["pilot_data_pack"]["missing_checks"] == ["business_reports"]
    assert report["acceptance_gate"]["blockers"][0]["reason"] == "pilot_data_incomplete"


def test_pilot_acceptance_report_keeps_readonly_boundary(monkeypatch):
    _patch_dependencies(monkeypatch)

    report = pilot_acceptance_report.summarize_pilot_acceptance_report(object(), tenant_id="demo_tenant")
    boundary = report["execution_boundary"]

    # 中文注释：验收报告只能输出证据，不能把“可验收”自动升级成真实签收或发布。
    assert boundary["readonly"] is True
    assert boundary["external_write_enabled"] is False
    assert boundary["auto_accept_enabled"] is False
    assert boundary["auto_release_enabled"] is False


def test_system_pilot_acceptance_report_returns_protected_report(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_pilot_acceptance_report",
        lambda db, tenant_id: {
            "report_version": "pilot_acceptance_report_v1",
            "overall_status": "accepted_with_warnings",
            "acceptance_gate": {"blocker_count": 0},
        },
    )

    response = system_router.get_pilot_acceptance_report(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"},
        db=object(),
    )

    assert response["code"] == 200
    assert response["data"]["report_version"] == "pilot_acceptance_report_v1"
    assert response["total"] == 0


def test_print_pilot_acceptance_report_script_exit_code(monkeypatch, capsys):
    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(print_pilot_acceptance_report, "SessionLocal", _SessionFactory())
    monkeypatch.setattr(
        print_pilot_acceptance_report,
        "summarize_pilot_acceptance_report",
        lambda db, tenant_id: {
            "report_version": "pilot_acceptance_report_v1",
            "overall_status": "accepted",
            "execution_boundary": {"auto_accept_enabled": False},
        },
    )

    exit_code = print_pilot_acceptance_report.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"report_version": "pilot_acceptance_report_v1"' in output
    assert '"auto_accept_enabled": false' in output
