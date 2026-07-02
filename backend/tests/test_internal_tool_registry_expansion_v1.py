from datetime import date

from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_shared_internal_tools
from app.modules.agent.platform import internal_tools
from app.modules.approval import service as approval_service
from app.modules.crm import service as crm_service
from app.modules.report import service as report_service


class _DummyDb:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if not self.responses:
            return _MappingResult()
        return self.responses.pop(0)


class _MappingResult:
    def __init__(self, *, rows=None, first=None):
        self._rows = rows or []
        self._first = first

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._first


def _tool_context(db=None):
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_demo",
        run_id="run_demo",
        db=db or _DummyDb(),
    )


def test_search_customers_supports_keyword_and_owner_filter():
    db = _DummyDb(
        [
            _MappingResult(
                rows=[
                    {
                        "customer_id": "cust_001",
                        "customer_name": "华东样例客户",
                        "owner_user_id": "u_sales_001",
                        "owner_user_name": "张三",
                        "lifecycle_stage": "opportunity",
                        "intent_level": "high",
                        "customer_level": "A",
                        "competitor_involved": 1,
                        "last_follow_up_at": None,
                        "next_follow_up_at": None,
                    }
                ]
            )
        ]
    )

    rows = crm_service.search_customers(
        db,
        {"tenant_id": "demo_tenant", "user_id": "u_manager", "permission_codes": ["crm:customer:read:team"]},
        keyword="华东",
        owner_user_id="u_sales_001",
        limit=30,
    )

    assert len(rows) == 1
    statement, params = db.calls[0]
    assert "c.customer_name LIKE :keyword" in statement
    assert "c.owner_user_id = :owner_user_id" in statement
    assert params["keyword"] == "%华东%"
    assert params["owner_user_id"] == "u_sales_001"
    assert params["limit"] == 30


def test_load_customer_detail_bundle_keeps_selected_risk_snapshot_at_front():
    db = _DummyDb(
        [
            _MappingResult(first={"customer_id": "cust_001", "customer_name": "样例客户", "owner_user_id": "u_sales_001"}),
            _MappingResult(
                rows=[
                    {
                        "risk_snapshot_id": "risk_latest",
                        "customer_id": "cust_001",
                        "rule_hits_json": "[]",
                        "evidence_json": "{}",
                        "suggested_task_json": "{}",
                    }
                ]
            ),
            _MappingResult(
                first={
                    "risk_snapshot_id": "risk_selected",
                    "customer_id": "cust_001",
                    "rule_hits_json": "[]",
                    "evidence_json": "{}",
                    "suggested_task_json": "{}",
                }
            ),
            _MappingResult(rows=[{"deal_id": "deal_001"}]),
            _MappingResult(rows=[{"follow_up_id": "fu_001"}]),
            _MappingResult(
                rows=[
                    {
                        "approval_id": "appr_001",
                        "proposed_payload_json": '{"title":"审批草稿"}',
                    }
                ]
            ),
            _MappingResult(rows=[{"task_id": "task_001", "approval_id": "appr_001"}]),
            _MappingResult(
                rows=[
                    {
                        "event_id": "event_001",
                        "approval_id": "appr_001",
                        "task_id": "task_001",
                        "detail_json": '{"status":"pending"}',
                    }
                ]
            ),
            _MappingResult(rows=[{"report_id": "report_001"}]),
        ]
    )

    detail = crm_service.load_customer_detail_bundle(
        db,
        {"tenant_id": "demo_tenant", "user_id": "u_manager", "permission_codes": ["crm:customer:read:team"]},
        "cust_001",
        risk_snapshot_id="risk_selected",
    )

    assert detail["selected_risk_snapshot_id"] == "risk_selected"
    assert detail["risk_snapshots"][0]["risk_snapshot_id"] == "risk_selected"
    assert detail["approvals"][0]["events"][0]["event_id"] == "event_001"
    assert detail["tasks"][0]["events"][0]["event_id"] == "event_001"


def test_query_reports_parses_json_payloads():
    db = _DummyDb(
        [
            _MappingResult(
                rows=[
                    {
                        "report_id": "report_001",
                        "report_type": "weekly",
                        "metrics_json": '{"won": 3}',
                        "risk_top_json": '[{"customer_id":"cust_001"}]',
                    }
                ]
            )
        ]
    )

    reports = report_service.query_reports(
        db,
        {"tenant_id": "demo_tenant", "user_id": "u_manager"},
        report_type="weekly",
    )

    assert reports[0]["metrics_json"] == {"won": 3}
    assert reports[0]["risk_top_json"] == [{"customer_id": "cust_001"}]


def test_create_approval_draft_inserts_record_and_logs_event(monkeypatch):
    db = _DummyDb([])
    logged: dict = {}

    monkeypatch.setattr(approval_service, "new_id", lambda prefix: f"{prefix}_demo_001")
    monkeypatch.setattr(approval_service, "log_workflow_event", lambda *args, **kwargs: logged.update(kwargs))

    result = approval_service.create_approval_draft(
        db,
        tenant_id="demo_tenant",
        customer_id="cust_001",
        proposed_payload={"title": "AI 回访任务", "priority": "high", "assignee_user_id": "u_sales_001"},
        requested_by_user_id="u_manager_001",
        risk_snapshot_id="risk_001",
        run_id="run_001",
    )

    assert result["approval_id"] == "appr_demo_001"
    assert result["status"] == "pending"
    assert db.calls
    statement, params = db.calls[0]
    assert "INSERT INTO approval_record" in statement
    assert params["customer_id"] == "cust_001"
    assert logged["approval_id"] == "appr_demo_001"
    assert logged["detail"]["title"] == "AI 回访任务"


def test_build_shared_internal_tools_supports_second_batch_handlers(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class _DummyJob:
        id = "job_demo_001"

    monkeypatch.setattr(
        internal_tools,
        "_load_current_user_context",
        lambda context: {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "permission_codes": [
                "crm:customer:read:self",
                "report:read:team",
                "agent:run:business_report",
            ],
        },
    )
    monkeypatch.setattr(
        internal_tools,
        "search_customers",
        lambda db, current_user, **kwargs: calls.append(("crm.search_customer", kwargs)) or [{"customer_id": "cust_001"}],
    )
    monkeypatch.setattr(
        internal_tools,
        "load_customer_detail_bundle",
        lambda db, current_user, customer_id, **kwargs: calls.append(
            ("crm.get_customer_detail", {"customer_id": customer_id, **kwargs})
        )
        or {"customer": {"customer_id": customer_id}},
    )
    monkeypatch.setattr(
        internal_tools,
        "query_reports",
        lambda db, current_user, **kwargs: calls.append(("report.query", kwargs)) or [{"report_id": "report_001"}],
    )
    monkeypatch.setattr(
        internal_tools,
        "enqueue_report_generation",
        lambda current_user, report_type, report_date: calls.append(
            (
                "report.generate",
                {"report_type": report_type, "report_date": report_date.isoformat() if report_date else None},
            )
        )
        or _DummyJob(),
    )
    monkeypatch.setattr(
        internal_tools,
        "create_approval_draft",
        lambda db, **kwargs: calls.append(("approval.create_draft", kwargs)) or {"approval_id": "appr_001"},
    )

    registry = InternalToolRegistry(build_shared_internal_tools())
    context = _tool_context()

    search_result = registry.execute("crm.search_customer", context, {"keyword": "华东", "limit": 5})
    detail_result = registry.execute("crm.get_customer_detail", context, {"customer_id": "cust_001"})
    report_query_result = registry.execute("report.query", context, {"report_type": "weekly"})
    report_generate_result = registry.execute(
        "report.generate",
        context,
        {"report_type": "monthly", "report_date": "2026-07-02"},
    )
    approval_result = registry.execute(
        "approval.create_draft",
        context,
        {"customer_id": "cust_001", "proposed_payload": {"title": "AI 审批草稿"}},
    )

    assert search_result["output"]["total"] == 1
    assert detail_result["output"]["customer"]["customer_id"] == "cust_001"
    assert report_query_result["output"]["total"] == 1
    assert report_generate_result["output"]["job_id"] == "job_demo_001"
    assert approval_result["output"]["approval_id"] == "appr_001"
    assert [name for name, _ in calls] == [
        "crm.search_customer",
        "crm.get_customer_detail",
        "report.query",
        "report.generate",
        "approval.create_draft",
    ]


def test_report_generate_tool_supports_iso_date_payload(monkeypatch):
    class _DummyJob:
        id = "job_demo_002"

    monkeypatch.setattr(
        internal_tools,
        "_load_current_user_context",
        lambda context: {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "permission_codes": ["agent:run:business_report"],
        },
    )
    monkeypatch.setattr(
        internal_tools,
        "enqueue_report_generation",
        lambda current_user, report_type, report_date: _DummyJob()
        if report_type == "weekly" and report_date == date(2026, 7, 2)
        else None,
    )

    registry = InternalToolRegistry(build_shared_internal_tools())
    result = registry.execute(
        "report.generate",
        _tool_context(),
        {"report_type": "weekly", "report_date": "2026-07-02"},
    )

    assert result["output"] == {
        "job_id": "job_demo_002",
        "report_type": "weekly",
        "report_date": "2026-07-02",
    }
