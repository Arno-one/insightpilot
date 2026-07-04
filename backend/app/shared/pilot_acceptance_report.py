from __future__ import annotations

from typing import Any, Literal

from app.shared.enterprise_hardening import summarize_enterprise_hardening
from app.shared.pilot_data_pack import summarize_pilot_data_pack
from app.shared.release_gate import summarize_release_gate
from app.shared.smoke_test_plan import summarize_smoke_test_plan

PilotAcceptanceStatus = Literal["accepted", "accepted_with_warnings", "blocked"]

PILOT_ACCEPTANCE_REPORT_VERSION = "pilot_acceptance_report_v1"


def _warning_release_items(release_gate: dict) -> list[str]:
    return [
        item["item_id"]
        for item in release_gate.get("items", [])
        if item.get("severity") == "warning"
    ]


def _blocker_release_items(release_gate: dict) -> list[str]:
    return [
        item["item_id"]
        for item in release_gate.get("items", [])
        if item.get("severity") == "blocker"
    ]


def _build_blockers(
    hardening: dict,
    release_gate: dict,
    smoke_plan: dict,
    pilot_data_pack: dict,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []

    hardening_blockers = hardening["stage_gate"]["must_fix_before_production"]
    if hardening_blockers:
        blockers.append(
            {
                "source": "enterprise_hardening",
                "reason": "enterprise_hardening_blocked",
                "items": hardening_blockers,
            }
        )

    release_blockers = _blocker_release_items(release_gate)
    if release_blockers or not release_gate["can_release_to_pilot"]:
        blockers.append(
            {
                "source": "release_gate",
                "reason": "pilot_release_blocked",
                "items": release_blockers or release_gate.get("manual_confirmation_required", []),
            }
        )

    if smoke_plan["overall_status"] != "ready":
        blockers.append(
            {
                "source": "smoke_test_plan",
                "reason": "smoke_plan_not_ready",
                "items": [smoke_plan["overall_status"]],
            }
        )

    if pilot_data_pack["overall_status"] != "ready":
        blockers.append(
            {
                "source": "pilot_data_pack",
                "reason": "pilot_data_incomplete",
                "items": pilot_data_pack["missing_checks"],
            }
        )

    return blockers


def _build_warnings(
    hardening: dict,
    release_gate: dict,
    pilot_data_pack: dict,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    hardening_warnings = hardening["stage_gate"]["should_fix_before_production"]
    if hardening_warnings:
        warnings.append(
            {
                "source": "enterprise_hardening",
                "reason": "production_warning_controls",
                "items": hardening_warnings,
            }
        )

    release_warnings = _warning_release_items(release_gate)
    if release_warnings:
        warnings.append(
            {
                "source": "release_gate",
                "reason": "manual_confirmation_required",
                "items": release_warnings,
            }
        )

    if pilot_data_pack["overall_status"] != "ready":
        warnings.append(
            {
                "source": "pilot_data_pack",
                "reason": "data_pack_requires_repair_before_demo",
                "items": pilot_data_pack["missing_checks"],
            }
        )

    return warnings


def summarize_pilot_acceptance_report(db: Any, *, tenant_id: str) -> dict:
    """中文注释：聚合企业试点验收所需证据，只读输出结论，不自动验收或触发真实外部动作。"""

    hardening = summarize_enterprise_hardening(tenant_id=tenant_id)
    release_gate = summarize_release_gate(tenant_id=tenant_id)
    smoke_plan = summarize_smoke_test_plan()
    pilot_data_pack = summarize_pilot_data_pack(db, tenant_id=tenant_id)

    blockers = _build_blockers(
        hardening=hardening,
        release_gate=release_gate,
        smoke_plan=smoke_plan,
        pilot_data_pack=pilot_data_pack,
    )
    warnings = _build_warnings(
        hardening=hardening,
        release_gate=release_gate,
        pilot_data_pack=pilot_data_pack,
    )

    can_enter_pilot = (
        not blockers
        and hardening["stage_gate"]["can_enter_enterprise_pilot"]
        and release_gate["can_release_to_pilot"]
        and pilot_data_pack["overall_status"] == "ready"
    )
    can_accept_pilot = can_enter_pilot and smoke_plan["overall_status"] == "ready"

    if blockers:
        overall_status: PilotAcceptanceStatus = "blocked"
    elif warnings:
        overall_status = "accepted_with_warnings"
    else:
        overall_status = "accepted"

    return {
        "report_version": PILOT_ACCEPTANCE_REPORT_VERSION,
        "tenant_id": tenant_id,
        "overall_status": overall_status,
        "acceptance_gate": {
            "can_enter_pilot": can_enter_pilot,
            "can_accept_pilot": can_accept_pilot,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "blockers": blockers,
            "warnings": warnings,
        },
        "sections": {
            "enterprise_hardening": {
                "version": hardening["hardening_version"],
                "overall_status": hardening["overall_status"],
                "control_count": hardening["control_count"],
                "status_counts": hardening["status_counts"],
            },
            "release_gate": {
                "version": release_gate["gate_version"],
                "release_decision": release_gate["release_decision"],
                "can_release_to_pilot": release_gate["can_release_to_pilot"],
                "can_release_to_production": release_gate["can_release_to_production"],
                "severity_counts": release_gate["severity_counts"],
            },
            "smoke_test_plan": {
                "version": smoke_plan["plan_version"],
                "overall_status": smoke_plan["overall_status"],
                "step_count": smoke_plan["step_count"],
                "priority_counts": smoke_plan["priority_counts"],
            },
            "pilot_data_pack": {
                "version": pilot_data_pack["pack_version"],
                "overall_status": pilot_data_pack["overall_status"],
                "check_count": pilot_data_pack["check_count"],
                "status_counts": pilot_data_pack["status_counts"],
                "missing_checks": pilot_data_pack["missing_checks"],
            },
        },
        "deliverables": [
            {
                "deliverable_id": "system_health_console",
                "title": "系统健康控制台",
                "source": "/system/health",
                "status": "ready",
            },
            {
                "deliverable_id": "release_gate_checklist",
                "title": "发布门禁清单",
                "source": "/api/system/release-gate",
                "status": release_gate["release_decision"],
            },
            {
                "deliverable_id": "smoke_test_plan",
                "title": "企业试点冒烟计划",
                "source": "/api/system/smoke-test-plan",
                "status": smoke_plan["overall_status"],
            },
            {
                "deliverable_id": "pilot_data_pack",
                "title": "企业试点数据覆盖包",
                "source": "/api/system/pilot-data-pack",
                "status": pilot_data_pack["overall_status"],
            },
        ],
        "execution_boundary": {
            "readonly": True,
            "external_write_enabled": False,
            "auto_accept_enabled": False,
            "auto_release_enabled": False,
            "description": "V1 仅生成企业试点验收报告，不代表真实客户签收，不触发发布、备份、恢复、外发或成本型外部集成。",
        },
    }
