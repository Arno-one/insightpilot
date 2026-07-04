from app.modules.system import router as system_router
from app.shared import pilot_data_pack
from scripts import print_pilot_data_pack


class _ScalarResult:
    def __init__(self, value: int):
        self.value = value

    def scalar_one(self):
        return self.value


class _DummyDb:
    def __init__(self, counts: dict[str, int]):
        self.counts = counts
        self.calls: list[tuple[str, dict | None]] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        table_name = sql.split("FROM ", 1)[1].split()[0]
        return _ScalarResult(self.counts.get(table_name, 0))


def _ready_counts() -> dict[str, int]:
    return {
        "tenant": 1,
        "sys_user": 3,
        "sys_role": 3,
        "crm_customer": 3,
        "customer_risk_snapshot": 1,
        "approval_record": 1,
        "sales_task": 1,
        "business_report": 1,
        "agent_run": 1,
    }


def test_pilot_data_pack_reports_ready_when_required_data_exists():
    db = _DummyDb(_ready_counts())
    pack = pilot_data_pack.summarize_pilot_data_pack(db, tenant_id="demo_tenant")

    assert pack["pack_version"] == "enterprise_pilot_data_pack_v1"
    assert pack["overall_status"] == "ready"
    assert pack["status_counts"] == {"pass": 9, "fail": 0}
    assert pack["missing_checks"] == []
    assert all(params == {"tenant_id": "demo_tenant"} for _, params in db.calls)


def test_pilot_data_pack_reports_clear_missing_items():
    counts = _ready_counts()
    counts["business_report"] = 0
    counts["agent_run"] = 0

    pack = pilot_data_pack.summarize_pilot_data_pack(_DummyDb(counts), tenant_id="demo_tenant")

    assert pack["overall_status"] == "incomplete"
    assert {"business_reports", "agent_trace_runs"}.issubset(set(pack["missing_checks"]))
    failed = {item["check_id"]: item for item in pack["checks"] if item["status"] == "fail"}
    assert failed["business_reports"]["recommendation"]
    assert failed["agent_trace_runs"]["expected_evidence"]


def test_pilot_data_pack_keeps_readonly_boundary():
    pack = pilot_data_pack.summarize_pilot_data_pack(_DummyDb(_ready_counts()), tenant_id="demo_tenant")
    boundary = pack["execution_boundary"]

    # 中文注释：试点数据包 V1 只做覆盖校验，不能自动修 seed 或写入演示数据。
    assert boundary["readonly"] is True
    assert boundary["data_mutation_enabled"] is False
    assert boundary["seed_repair_enabled"] is False


def test_system_pilot_data_pack_returns_protected_pack(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_pilot_data_pack",
        lambda db, tenant_id: {
            "pack_version": "enterprise_pilot_data_pack_v1",
            "overall_status": "ready",
            "check_count": 9,
            "status_counts": {"pass": 9, "fail": 0},
        },
    )

    response = system_router.get_pilot_data_pack(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"},
        db=_DummyDb({}),
    )

    assert response["code"] == 200
    assert response["data"]["pack_version"] == "enterprise_pilot_data_pack_v1"
    assert response["total"] == 9


def test_print_pilot_data_pack_script_exit_code(monkeypatch, capsys):
    class _SessionFactory:
        def __call__(self):
            return self

        def __enter__(self):
            return _DummyDb(_ready_counts())

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(print_pilot_data_pack, "SessionLocal", _SessionFactory())

    exit_code = print_pilot_data_pack.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"pack_version": "enterprise_pilot_data_pack_v1"' in output
    assert '"seed_repair_enabled": false' in output
