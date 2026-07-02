from datetime import date

from app.modules.agent.graphs import business_report_graph
from app.modules.report import router as report_router
from app.workers import report_jobs


class _DummyJob:
    def __init__(self, job_id: str):
        self.id = job_id


class _DummyQueue:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def enqueue(self, job_name: str, *args, **kwargs):
        self.calls.append((job_name, args, kwargs))
        return _DummyJob(f"job_{len(self.calls)}")


def test_resolve_report_period_for_daily():
    result = business_report_graph._resolve_report_period("daily", date(2026, 7, 2))

    assert result == {
        "period_start": date(2026, 7, 2),
        "period_end": date(2026, 7, 2),
        "previous_period_start": date(2026, 7, 1),
        "previous_period_end": date(2026, 7, 1),
    }


def test_resolve_report_period_for_weekly():
    # 中文注释：周报按自然周取值，确保前端看到的趋势对比口径始终是“本周 vs 上周”。
    result = business_report_graph._resolve_report_period("weekly", date(2026, 7, 2))

    assert result == {
        "period_start": date(2026, 6, 29),
        "period_end": date(2026, 7, 5),
        "previous_period_start": date(2026, 6, 22),
        "previous_period_end": date(2026, 6, 28),
    }


def test_resolve_report_period_for_monthly():
    # 中文注释：月报需要正确跨年回看上月，否则 1 月份的趋势对比很容易直接算错。
    result = business_report_graph._resolve_report_period("monthly", date(2026, 1, 15))

    assert result == {
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "previous_period_start": date(2025, 12, 1),
        "previous_period_end": date(2025, 12, 31),
    }


def test_enqueue_report_generation_supports_report_type_and_anchor_date(monkeypatch):
    dummy_queue = _DummyQueue()
    monkeypatch.setattr(report_router, "get_default_queue", lambda: dummy_queue)

    job = report_router._enqueue_report_generation(
        {"tenant_id": "demo_tenant", "user_id": "u_manager_001"},
        "weekly",
        date(2026, 7, 2),
    )

    assert job.id == "job_1"
    assert dummy_queue.calls == [
        (
            "app.workers.report_jobs.generate_business_report",
            ("demo_tenant", "u_manager_001", "weekly", "2026-07-02"),
            {"job_timeout": 600},
        )
    ]


def test_generate_daily_report_keeps_backward_compatibility(monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_run_business_report_workflow(tenant_id: str, user_id: str, report_type: str = "daily", report_date: str | None = None):
        captured.update(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "report_type": report_type,
                "report_date": report_date,
            }
        )
        return {"status": "success", "run_id": "run_demo_001"}

    monkeypatch.setattr(report_jobs, "run_business_report_workflow", fake_run_business_report_workflow)

    result = report_jobs.generate_daily_report("demo_tenant", "u_manager_001")

    assert result["status"] == "success"
    assert captured == {
        "tenant_id": "demo_tenant",
        "user_id": "u_manager_001",
        "report_type": "daily",
        "report_date": None,
    }


class _DummyResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _DummySession:
    def __init__(self):
        self.statement = ""
        self.params: dict = {}

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _DummyResult()


def test_list_reports_supports_owner_drilldown_filter():
    dummy_db = _DummySession()

    report_router.list_reports(
        owner_user_id="u_sales_001",
        current_user={"tenant_id": "demo_tenant", "user_id": "u_manager_001"},
        db=dummy_db,
    )

    assert "CAST(br.metrics_json AS CHAR) LIKE :owner_pattern" in dummy_db.statement
    assert "CAST(br.risk_top_json AS CHAR) LIKE :owner_pattern" in dummy_db.statement
    assert dummy_db.params["owner_pattern"] == "%u_sales_001%"
