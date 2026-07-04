from fastapi.testclient import TestClient

from app.main import app
from app.modules.nl2sql import service as nl2sql_service
from tests.test_agent_chat_api_v1 import _build_headers, _cleanup_agent_chat_sessions, _ensure_agent_chat_tables_exist
from tests.test_nl2sql_persistence_v1 import _cleanup_nl2sql_fixture, _ensure_nl2sql_tables_exist
from tests.test_nl2sql_query_pipeline_v1 import _cleanup_probe_rows, _ensure_probe_table_exists, _seed_probe_rows


def test_unified_agent_chat_runs_nl2sql_tool_for_data_query(monkeypatch):
    _ensure_agent_chat_tables_exist()
    _ensure_nl2sql_tables_exist()
    _ensure_probe_table_exists()
    nl2sql_service._cache.clear()
    client = TestClient(app)
    headers, tenant_id, _ = _build_headers(client)
    session_ids: list[str] = []
    _seed_probe_rows(tenant_id)

    monkeypatch.setattr(nl2sql_service, "build_schema_text", lambda: "nl2sql_probe(tenant_id, probe_id, label, is_deleted)")
    monkeypatch.setattr(nl2sql_service, "get_tables_with_column", lambda column_name: {"nl2sql_probe"})
    monkeypatch.setattr(
        nl2sql_service,
        "generate_sql",
        lambda question, schema_text=None: (
            "SELECT probe_id, label FROM nl2sql_probe WHERE tenant_id = :tenant_id ORDER BY probe_id",
            9,
        ),
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={"agent_scope": "general", "intent": "unknown", "title": "NL2SQL 工具接入测试"},
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "intent": "data_query", "content": "列出测试数据"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]

        assert data["runtime"]["handled"] is True
        assert data["runtime"]["handler"] == "data.query_sql"
        assert data["assistant_message"]["tool_name"] == "data.query_sql"
        assert "查询完成，返回 1 行数据" in data["assistant_message"]["content"]
        assert data["assistant_message"]["metadata_json"]["row_count"] == 1
        assert "nl2sql_probe.is_deleted = 0" in data["assistant_message"]["metadata_json"]["sql"]
        assert data["session"]["message_count"] == 2

        detail_response = client.get(f"/api/agent/chat/sessions/{session_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]
        assert [item["role"] for item in detail["messages"]] == ["user", "assistant"]
    finally:
        nl2sql_service._cache.clear()
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_probe_rows(tenant_id)
        _cleanup_nl2sql_fixture(tenant_id)
