from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.shared.pilot_acceptance_report import summarize_pilot_acceptance_report
from app.shared.smoke_test_plan import summarize_smoke_test_plan

RunbookStatus = Literal["ready", "ready_with_warnings", "blocked"]

PILOT_OPERATIONS_RUNBOOK_VERSION = "pilot_operations_runbook_v1"


@dataclass(frozen=True, slots=True)
class RunbookCadence:
    cadence_id: str
    title: str
    frequency: str
    owner_role: str
    steps: list[str]
    evidence: list[str]

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IncidentLevel:
    level: str
    trigger: str
    owner_role: str
    response_target: str
    escalation_path: list[str]
    allowed_actions: list[str]

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OperatorBoundary:
    boundary_id: str
    title: str
    allowed: bool
    description: str

    def model_dump(self) -> dict:
        return asdict(self)


def _derive_status(acceptance_report: dict) -> RunbookStatus:
    if acceptance_report["overall_status"] == "blocked":
        return "blocked"
    if acceptance_report["overall_status"] == "accepted_with_warnings":
        return "ready_with_warnings"
    return "ready"


def _build_watch_items(acceptance_report: dict) -> list[dict]:
    gate = acceptance_report["acceptance_gate"]
    items: list[dict] = []
    for blocker in gate["blockers"]:
        items.append({**blocker, "severity": "blocker"})
    for warning in gate["warnings"]:
        items.append({**warning, "severity": "warning"})
    return items


def _build_cadences(smoke_plan: dict) -> list[RunbookCadence]:
    p0_steps = [
        step["step_id"]
        for step in smoke_plan["steps"]
        if step["priority"] == "p0"
    ]
    return [
        RunbookCadence(
            cadence_id="daily_health_review",
            title="每日健康巡检",
            frequency="daily",
            owner_role="pilot_operator",
            steps=[
                "查看系统健康控制台总体状态",
                "确认验收报告没有新增阻断项",
                "复核失败通知、Agent Trace 异常和关键页面加载状态",
            ],
            evidence=["/system/health", "/api/system/pilot-acceptance-report"],
        ),
        RunbookCadence(
            cadence_id="p0_smoke_review",
            title="P0 冒烟复核",
            frequency="before_pilot_demo",
            owner_role="pilot_operator",
            steps=p0_steps,
            evidence=["/api/system/smoke-test-plan"],
        ),
        RunbookCadence(
            cadence_id="weekly_release_gate_review",
            title="每周发布门禁复核",
            frequency="weekly",
            owner_role="system_admin",
            steps=[
                "复核发布门禁 warning 是否已有人工确认",
                "确认部署就绪和备份恢复仍无 blocker",
                "整理下一周生产前修复建议",
            ],
            evidence=["/api/system/release-gate", "/api/system/deployment-readiness"],
        ),
    ]


def _build_incident_levels() -> list[IncidentLevel]:
    return [
        IncidentLevel(
            level="p0",
            trigger="登录不可用、核心 CRM 查询不可用、租户边界异常或验收报告出现 blocker",
            owner_role="system_admin",
            response_target="30m 内完成初判并给出人工处置路径",
            escalation_path=["pilot_operator", "system_admin", "engineering_owner"],
            allowed_actions=["只读排查", "暂停试点演示", "记录人工复盘结论"],
        ),
        IncidentLevel(
            level="p1",
            trigger="Agent Trace、NL2SQL、RAG、通知状态或审批任务出现局部不可用",
            owner_role="pilot_operator",
            response_target="4h 内完成复核并归档影响范围",
            escalation_path=["pilot_operator", "engineering_owner"],
            allowed_actions=["只读复核", "补充试点说明", "创建后续修复任务"],
        ),
        IncidentLevel(
            level="p2",
            trigger="展示文案、非阻断 warning、演示数据补齐建议或体验优化项",
            owner_role="pilot_operator",
            response_target="下一次迭代排期前完成归类",
            escalation_path=["pilot_operator"],
            allowed_actions=["记录建议", "合并到后续 VNext backlog"],
        ),
    ]


def _build_operator_boundaries() -> list[OperatorBoundary]:
    return [
        OperatorBoundary(
            boundary_id="no_external_write",
            title="禁止真实外发",
            allowed=False,
            description="试点运营手册不允许触发真实邮件、短信、日历、企业微信、飞书或第三方系统写入。",
        ),
        OperatorBoundary(
            boundary_id="no_destructive_recovery",
            title="禁止真实恢复和覆盖",
            allowed=False,
            description="未获得暂停确认前，不执行真实备份恢复、删除、覆盖或跨环境迁移。",
        ),
        OperatorBoundary(
            boundary_id="readonly_evidence",
            title="允许只读证据复核",
            allowed=True,
            description="允许查看健康控制台、发布门禁、验收报告、冒烟计划和试点数据覆盖报告。",
        ),
        OperatorBoundary(
            boundary_id="manual_confirmation_required",
            title="人工确认边界",
            allowed=True,
            description="涉及成本、外部集成、生产安全、合规和隐私策略时必须暂停确认。",
        ),
    ]


def summarize_pilot_operations_runbook(db: Any, *, tenant_id: str) -> dict:
    """中文注释：生成企业试点运营手册，只读聚合验收状态与人工值守流程，不写入任何运营记录。"""

    acceptance_report = summarize_pilot_acceptance_report(db, tenant_id=tenant_id)
    smoke_plan = summarize_smoke_test_plan()
    status = _derive_status(acceptance_report)
    cadences = _build_cadences(smoke_plan)
    incident_levels = _build_incident_levels()
    operator_boundaries = _build_operator_boundaries()
    watch_items = _build_watch_items(acceptance_report)

    return {
        "runbook_version": PILOT_OPERATIONS_RUNBOOK_VERSION,
        "tenant_id": tenant_id,
        "overall_status": status,
        "pilot_operable": status != "blocked",
        "source_report_version": acceptance_report["report_version"],
        "acceptance_status": acceptance_report["overall_status"],
        "watch_item_count": len(watch_items),
        "watch_items": watch_items,
        "cadence_count": len(cadences),
        "cadences": [cadence.model_dump() for cadence in cadences],
        "incident_levels": [level.model_dump() for level in incident_levels],
        "operator_boundaries": [boundary.model_dump() for boundary in operator_boundaries],
        "handoff_checklist": [
            {
                "item_id": deliverable["deliverable_id"],
                "title": deliverable["title"],
                "source": deliverable["source"],
                "status": deliverable["status"],
            }
            for deliverable in acceptance_report["deliverables"]
        ],
        "execution_boundary": {
            "readonly": True,
            "external_write_enabled": False,
            "auto_execute_enabled": False,
            "operator_record_persistence_enabled": False,
            "description": "V1 只输出试点运营手册和人工值守流程，不写入运营记录、不触发外部系统、不执行恢复或发布。",
        },
    }
