from app.modules.agent.platform import InternalToolRegistry, ToolExecutionContext, build_data_mcp_tools, build_shared_mcp_gateway
from app.modules.agent.platform import data_mcp_tools


class _DummyDb:
    pass


def _tool_context():
    return ToolExecutionContext(
        tenant_id="demo_tenant",
        user_id="u_demo",
        run_id="run_demo",
        db=_DummyDb(),
        readonly_db=_DummyDb(),
    )


def _patch_user_context(monkeypatch):
    monkeypatch.setattr(
        data_mcp_tools,
        "_load_current_user_context",
        lambda context: {
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "permission_codes": ["crm:customer:read:self"],
        },
    )


def test_data_query_sql_tool_returns_standard_protocol_payload(monkeypatch):
    _patch_user_context(monkeypatch)
    monkeypatch.setattr(
        data_mcp_tools.nl2sql_service,
        "query",
        lambda db_rw, db_readonly, current_user, *, question, session_id=None: {
            "session_id": session_id or "nl2sql_sess_demo",
            "query_id": "nl2sql_query_demo",
            "sql": "SELECT COUNT(*) AS customer_count FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 100",
            "result": {"columns": ["customer_count"], "rows": [{"customer_count": 3}], "row_count": 1},
            "is_cached": False,
            "cost_ms": 7,
        },
    )

    registry = InternalToolRegistry(build_data_mcp_tools())
    result = registry.execute("data.query_sql", _tool_context(), {"question": "客户总数是多少？"})
    output = result["output"]

    assert result["tool_name"] == "data.query_sql"
    assert output["protocol"] == "data.query_sql.v1"
    assert output["query_id"] == "nl2sql_query_demo"
    assert output["row_count"] == 1
    assert output["trace"]["status"] == "executed"
    assert output["trace"]["question"] == "客户总数是多少？"


def test_shared_mcp_gateway_exposes_and_executes_data_mcp(monkeypatch):
    _patch_user_context(monkeypatch)
    monkeypatch.setattr(
        data_mcp_tools.nl2sql_service,
        "query",
        lambda db_rw, db_readonly, current_user, *, question, session_id=None: {
            "session_id": "nl2sql_sess_demo",
            "query_id": "nl2sql_query_demo",
            "sql": "SELECT 1 AS ok FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 100",
            "result": {"columns": ["ok"], "rows": [{"ok": 1}], "row_count": 1},
            "is_cached": True,
            "cost_ms": 0,
        },
    )

    gateway = build_shared_mcp_gateway()
    specs = gateway.list_tool_specs()
    result = gateway.execute("data.query_sql", _tool_context(), {"question": "测试数据查询"})

    assert "data.query_sql" in {item["name"] for item in specs}
    assert "data" in {item["server_name"] for item in specs}
    assert result["server_name"] == "data"
    assert result["tool_name"] == "data.query_sql"
    assert result["output"]["is_cached"] is True
    assert result["audit_record"]["trace_summary"]["query_id"] == "nl2sql_query_demo"
    assert result["audit_record"]["trace_summary"]["is_cached"] is True


def test_data_query_sql_tool_injects_followup_context(monkeypatch):
    _patch_user_context(monkeypatch)
    captured: dict = {}

    def fake_query(db_rw, db_readonly, current_user, *, question, session_id=None):
        captured["question"] = question
        captured["session_id"] = session_id
        return {
            "session_id": session_id,
            "query_id": "nl2sql_query_followup",
            "sql": "SELECT customer_id FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 100",
            "result": {"columns": ["customer_id"], "rows": [], "row_count": 0},
            "is_cached": False,
            "cost_ms": 5,
        }

    monkeypatch.setattr(data_mcp_tools.nl2sql_service, "query", fake_query)

    registry = InternalToolRegistry(build_data_mcp_tools())
    output = registry.execute(
        "data.query_sql",
        _tool_context(),
        {
            "question": "只看高风险的",
            "session_id": "nl2sql_sess_previous",
            "context": {
                "question": "本月客户有哪些？",
                "sql": "SELECT customer_id FROM crm_customer WHERE tenant_id = :tenant_id LIMIT 100",
            },
        },
    )["output"]

    assert captured["session_id"] == "nl2sql_sess_previous"
    assert "上一轮数据查询上下文" in captured["question"]
    assert "上一轮SQL" in captured["question"]
    assert "只看高风险的" in captured["question"]
    assert output["question"] == "只看高风险的"
    assert output["followup_context"]["question"] == "本月客户有哪些？"
