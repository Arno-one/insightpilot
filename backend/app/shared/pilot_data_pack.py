from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy import text

PilotDataStatus = Literal["pass", "fail"]

PILOT_DATA_PACK_VERSION = "enterprise_pilot_data_pack_v1"


@dataclass(frozen=True, slots=True)
class PilotDataCheckSpec:
    """中文注释：定义一个企业试点数据覆盖检查项，SQL 只允许来自代码常量。"""

    check_id: str
    category: str
    title: str
    table_name: str
    required_min_count: int
    tenant_scoped: bool
    expected_evidence: str
    recommendation: str


@dataclass(frozen=True, slots=True)
class PilotDataCheckResult:
    check_id: str
    category: str
    title: str
    status: PilotDataStatus
    table_name: str
    required_min_count: int
    actual_count: int
    expected_evidence: str
    recommendation: str

    def model_dump(self) -> dict:
        return asdict(self)


PILOT_DATA_CHECKS: tuple[PilotDataCheckSpec, ...] = (
    PilotDataCheckSpec(
        check_id="tenant_baseline",
        category="tenant",
        title="试点租户存在",
        table_name="tenant",
        required_min_count=1,
        tenant_scoped=True,
        expected_evidence="当前 tenant_id 能在 tenant 表中查询到。",
        recommendation="先执行租户初始化脚本，确保试点租户存在。",
    ),
    PilotDataCheckSpec(
        check_id="demo_accounts",
        category="identity",
        title="演示账号覆盖",
        table_name="sys_user",
        required_min_count=3,
        tenant_scoped=True,
        expected_evidence="至少包含管理员、主管、销售等试点账号。",
        recommendation="补齐管理员、销售主管和销售员演示账号。",
    ),
    PilotDataCheckSpec(
        check_id="role_matrix",
        category="identity",
        title="角色矩阵覆盖",
        table_name="sys_role",
        required_min_count=3,
        tenant_scoped=True,
        expected_evidence="至少包含 admin、manager、salesperson 等角色。",
        recommendation="补齐试点角色和用户角色关系。",
    ),
    PilotDataCheckSpec(
        check_id="crm_customers",
        category="crm",
        title="客户样例覆盖",
        table_name="crm_customer",
        required_min_count=3,
        tenant_scoped=True,
        expected_evidence="客户工作台有可检索、可进入详情的样例客户。",
        recommendation="补齐客户、联系人、商机和跟进样例数据。",
    ),
    PilotDataCheckSpec(
        check_id="risk_snapshots",
        category="risk",
        title="风险快照覆盖",
        table_name="customer_risk_snapshot",
        required_min_count=1,
        tenant_scoped=True,
        expected_evidence="风险中心能展示至少一个客户风险快照。",
        recommendation="执行风险扫描或补齐风险快照演示数据。",
    ),
    PilotDataCheckSpec(
        check_id="approval_records",
        category="approval",
        title="审批记录覆盖",
        table_name="approval_record",
        required_min_count=1,
        tenant_scoped=True,
        expected_evidence="审批页能展示至少一条 AI 动作审批记录。",
        recommendation="补齐审批草稿或历史审批演示数据。",
    ),
    PilotDataCheckSpec(
        check_id="sales_tasks",
        category="task",
        title="销售任务覆盖",
        table_name="sales_task",
        required_min_count=1,
        tenant_scoped=True,
        expected_evidence="销售任务页能展示待办、状态和负责人。",
        recommendation="补齐试点销售任务样例。",
    ),
    PilotDataCheckSpec(
        check_id="business_reports",
        category="report",
        title="经营报告覆盖",
        table_name="business_report",
        required_min_count=1,
        tenant_scoped=True,
        expected_evidence="经营报告页能展示日报、周报或月报样例。",
        recommendation="补齐经营报告演示数据或执行报告生成任务。",
    ),
    PilotDataCheckSpec(
        check_id="agent_trace_runs",
        category="agent",
        title="Agent Trace 覆盖",
        table_name="agent_run",
        required_min_count=1,
        tenant_scoped=True,
        expected_evidence="Agent 追踪页能打开至少一条运行记录。",
        recommendation="补齐 Agent 运行记录和步骤链路演示数据。",
    ),
)


def _count_rows(db: Any, *, table_name: str, tenant_id: str, tenant_scoped: bool) -> int:
    if tenant_scoped:
        statement = text(f"SELECT COUNT(*) FROM {table_name} WHERE tenant_id = :tenant_id")
        return int(db.execute(statement, {"tenant_id": tenant_id}).scalar_one())
    statement = text(f"SELECT COUNT(*) FROM {table_name}")
    return int(db.execute(statement).scalar_one())


def summarize_pilot_data_pack(db: Any, *, tenant_id: str) -> dict:
    """中文注释：只读校验企业试点数据覆盖，不写入、不修复、不触发任务。"""

    checks: list[PilotDataCheckResult] = []
    for spec in PILOT_DATA_CHECKS:
        actual_count = _count_rows(
            db,
            table_name=spec.table_name,
            tenant_id=tenant_id,
            tenant_scoped=spec.tenant_scoped,
        )
        status: PilotDataStatus = "pass" if actual_count >= spec.required_min_count else "fail"
        checks.append(
            PilotDataCheckResult(
                check_id=spec.check_id,
                category=spec.category,
                title=spec.title,
                status=status,
                table_name=spec.table_name,
                required_min_count=spec.required_min_count,
                actual_count=actual_count,
                expected_evidence=spec.expected_evidence,
                recommendation=spec.recommendation,
            )
        )

    status_counts = {"pass": 0, "fail": 0}
    category_counts: dict[str, int] = {}
    for check in checks:
        status_counts[check.status] += 1
        category_counts[check.category] = category_counts.get(check.category, 0) + 1

    return {
        "pack_version": PILOT_DATA_PACK_VERSION,
        "tenant_id": tenant_id,
        "overall_status": "ready" if status_counts["fail"] == 0 else "incomplete",
        "check_count": len(checks),
        "status_counts": status_counts,
        "category_counts": category_counts,
        "checks": [check.model_dump() for check in checks],
        "missing_checks": [check.check_id for check in checks if check.status == "fail"],
        "execution_boundary": {
            "readonly": True,
            "data_mutation_enabled": False,
            "seed_repair_enabled": False,
            "description": "V1 只读校验试点数据完整性，不修改 seed SQL、不写数据库、不生成演示数据。",
        },
    }
