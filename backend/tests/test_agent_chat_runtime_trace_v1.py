from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app
from app.modules.agent import followup_strategy_tool
from tests.test_agent_chat_api_v1 import (
    _build_headers,
    _cleanup_agent_chat_sessions,
    _cleanup_risk_chat_customer_fixture,
    _create_risk_chat_customer_fixture,
    _ensure_agent_chat_tables_exist,
)


def _cleanup_agent_runtime_trace(tenant_id: str, run_id: str | None):
    if not run_id:
        return
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM agent_run_plan_step WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.execute(
            text("DELETE FROM agent_run_plan WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.execute(
            text("DELETE FROM agent_step WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.execute(
            text("DELETE FROM agent_run WHERE tenant_id = :tenant_id AND run_id = :run_id"),
            {"tenant_id": tenant_id, "run_id": run_id},
        )
        db.commit()


def _ensure_agent_runtime_plan_tables_exist():
    with SessionLocal() as db:
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_run_plan (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  plan_id VARCHAR(64) NOT NULL,
                  run_id VARCHAR(64) NOT NULL,
                  user_id VARCHAR(64) NOT NULL,
                  plan_type VARCHAR(50) NOT NULL DEFAULT 'single_tool',
                  plan_title VARCHAR(120) NOT NULL,
                  objective_summary TEXT NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'created',
                  source_intent VARCHAR(50) NULL,
                  planned_at DATETIME NOT NULL,
                  started_at DATETIME NULL,
                  finished_at DATETIME NULL,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_plan_id (plan_id),
                  KEY idx_tenant_run (tenant_id, run_id),
                  KEY idx_tenant_user_planned (tenant_id, user_id, planned_at),
                  KEY idx_tenant_status_planned (tenant_id, status, planned_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agent_run_plan_step (
                  id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  tenant_id VARCHAR(64) NOT NULL,
                  plan_step_id VARCHAR(64) NOT NULL,
                  plan_id VARCHAR(64) NOT NULL,
                  run_id VARCHAR(64) NOT NULL,
                  step_code VARCHAR(80) NOT NULL,
                  step_order INT NOT NULL,
                  step_title VARCHAR(120) NOT NULL,
                  step_type VARCHAR(50) NOT NULL DEFAULT 'tool_call',
                  tool_name VARCHAR(80) NULL,
                  depends_on_json JSON NULL,
                  status VARCHAR(30) NOT NULL DEFAULT 'created',
                  input_summary TEXT NULL,
                  output_summary TEXT NULL,
                  linked_step_id VARCHAR(64) NULL,
                  error_message TEXT NULL,
                  metadata_json JSON NULL,
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                  UNIQUE KEY uk_plan_step_id (plan_step_id),
                  KEY idx_tenant_plan_order (tenant_id, plan_id, step_order),
                  KEY idx_tenant_run (tenant_id, run_id),
                  KEY idx_tenant_status (tenant_id, status),
                  KEY idx_linked_step_id (linked_step_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
        )
        db.commit()


def test_unified_agent_chat_runtime_writes_agent_trace(monkeypatch):
    _ensure_agent_chat_tables_exist()
    _ensure_agent_runtime_plan_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []
    run_id: str | None = None

    monkeypatch.setattr(
        followup_strategy_tool,
        "run_followup_strategy_tool",
        lambda db_rw, current_user, *, customer_id, question: {
            "reply": "跟进策略已生成。",
            "strategy_result": {
                "protocol": "followup.strategy.v1",
                "customer_id": customer_id,
                "strategy_level": "rescue",
                "recommended_actions": [
                    {
                        "source": "follow_up_strategy",
                        "customer_id": customer_id,
                        "requires_approval": True,
                    }
                ],
                "recommended_action_count": 1,
            },
            "tool_name": "followup.plan_strategy",
            "customer_id": customer_id,
            "strategy_level": "rescue",
            "recommended_actions": [
                {
                    "source": "follow_up_strategy",
                    "customer_id": customer_id,
                    "requires_approval": True,
                }
            ],
            "recommended_action_count": 1,
            "error": None,
        },
    )

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "统一对话 Trace 测试",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我生成这个客户的跟进策略"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]
        run_id = data["assistant_message"]["run_id"]

        assert data["runtime"]["run_id"] == run_id
        assert len(data["runtime"]["step_ids"]) == 4
        assert data["runtime"]["step_id"] == data["runtime"]["step_ids"][-1]
        assert data["runtime"]["plan_id"].startswith("plan_")
        assert len(data["runtime"]["plan_step_ids"]) == 4
        assert data["runtime"]["plan_step_id"].startswith("pstep_")
        assert data["runtime"]["planner"]["planner"] == "template_planner_v1"
        assert data["runtime"]["tool_route"]["selected_tool"] == "followup.plan_strategy"
        assert data["assistant_message"]["metadata_json"]["runtime_run_id"] == run_id
        assert data["assistant_message"]["metadata_json"]["runtime_step_id"].startswith("step_")
        assert data["assistant_message"]["metadata_json"]["runtime_step_ids"] == data["runtime"]["step_ids"]
        assert data["assistant_message"]["metadata_json"]["runtime_plan_id"] == data["runtime"]["plan_id"]
        assert data["assistant_message"]["metadata_json"]["runtime_planner"]["handler"] == "followup.plan_strategy"
        assert data["assistant_message"]["metadata_json"]["runtime_tool_route"]["selected_tool"] == "followup.plan_strategy"

        detail_response = client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["run"]["run_type"] == "agent_chat_runtime"
        assert detail["run"]["graph_name"] == "unified_agent_chat_runtime"
        assert detail["run"]["status"] == "success"
        assert len(detail["steps"]) == 4
        assert detail["steps"][0]["node_name"] == "agent_chat_intent_route"
        assert detail["steps"][0]["tool_name"] == "intent_router"
        assert detail["steps"][1]["node_name"] == "agent_chat_planner"
        assert detail["steps"][1]["tool_name"] == "template_planner_v1"
        assert detail["steps"][1]["output_json"]["steps"][0]["step_code"] == "load_context"
        assert detail["steps"][2]["node_name"] == "agent_chat_tool_router"
        assert detail["steps"][2]["tool_name"] == "agent_chat_tool_router_v1"
        assert detail["steps"][2]["output_json"]["selected_tool"] == "followup.plan_strategy"
        assert detail["steps"][3]["node_name"] == "agent_chat_tool"
        assert detail["steps"][3]["tool_name"] == "followup.plan_strategy"
        assert detail["plans"][0]["plan_id"] == data["runtime"]["plan_id"]
        assert detail["plans"][0]["plan_type"] == "multi_step"
        assert detail["plans"][0]["status"] == "success"
        assert len(detail["plans"][0]["steps"]) == 4
        assert detail["plans"][0]["steps"][0]["depends_on_json"] == []
        assert detail["plans"][0]["steps"][1]["depends_on_json"] == ["intent_route"]
        assert detail["plans"][0]["steps"][2]["depends_on_json"] == ["template_planner"]
        assert detail["plans"][0]["steps"][3]["linked_step_id"] == data["runtime"]["step_id"]
        assert detail["plans"][0]["steps"][3]["depends_on_json"] == ["tool_router"]
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_agent_runtime_trace(tenant_id, run_id)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_unified_agent_chat_runtime_writes_failed_agent_trace(monkeypatch):
    _ensure_agent_chat_tables_exist()
    _ensure_agent_runtime_plan_tables_exist()
    client = TestClient(app)
    headers, tenant_id, user_id = _build_headers(client)
    customer_id, risk_snapshot_id = _create_risk_chat_customer_fixture(tenant_id, user_id)
    session_ids: list[str] = []
    run_id: str | None = None
    retry_run_id: str | None = None
    resume_run_id: str | None = None

    def raise_followup_error(*args, **kwargs):
        raise RuntimeError("策略工具模拟失败")

    monkeypatch.setattr(followup_strategy_tool, "run_followup_strategy_tool", raise_followup_error)

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "customer",
                "intent": "unknown",
                "title": "统一对话失败 Trace 测试",
                "related_customer_id": customer_id,
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        message_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "帮我生成这个客户的跟进策略"},
        )
        assert message_response.status_code == 200
        data = message_response.json()["data"]
        run_id = data["assistant_message"]["run_id"]

        assert data["runtime"]["status"] == "failed"
        assert data["runtime"]["run_id"] == run_id
        assert len(data["runtime"]["step_ids"]) == 4
        assert data["runtime"]["step_id"] == data["runtime"]["step_ids"][-1]
        assert data["runtime"]["plan_id"].startswith("plan_")
        assert len(data["runtime"]["plan_step_ids"]) == 4
        assert data["runtime"]["plan_step_id"].startswith("pstep_")
        assert "策略工具模拟失败" in data["runtime"]["error"]
        assert data["runtime"]["recovery_plan"][0]["action"] == "inspect_trace"
        assert data["assistant_message"]["metadata_json"]["runtime_status"] == "failed"
        assert data["assistant_message"]["metadata_json"]["recovery_plan"]

        detail_response = client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]
        failed_step_id = detail["steps"][3]["step_id"]

        assert detail["run"]["run_type"] == "agent_chat_runtime"
        assert detail["run"]["status"] == "failed"
        assert "策略工具模拟失败" in detail["run"]["error_message"]
        assert detail["run"]["output_json"]["recovery_plan"][0]["action"] == "inspect_trace"
        assert len(detail["steps"]) == 4
        assert detail["steps"][0]["status"] == "success"
        assert detail["steps"][0]["tool_name"] == "intent_router"
        assert detail["steps"][1]["status"] == "success"
        assert detail["steps"][1]["tool_name"] == "template_planner_v1"
        assert detail["steps"][2]["status"] == "success"
        assert detail["steps"][2]["tool_name"] == "agent_chat_tool_router_v1"
        assert detail["steps"][3]["status"] == "failed"
        assert detail["steps"][3]["tool_name"] == "followup.plan_strategy"
        assert detail["plans"][0]["status"] == "failed"
        assert len(detail["plans"][0]["steps"]) == 4
        assert detail["plans"][0]["steps"][0]["status"] == "success"
        assert detail["plans"][0]["steps"][1]["status"] == "success"
        assert detail["plans"][0]["steps"][2]["status"] == "success"
        assert detail["plans"][0]["steps"][3]["status"] == "failed"
        assert "策略工具模拟失败" in detail["plans"][0]["steps"][3]["error_message"]

        monkeypatch.setattr(
            followup_strategy_tool,
            "run_followup_strategy_tool",
            lambda db_rw, current_user, *, customer_id, question: {
                "reply": "重试后的跟进策略已生成。",
                "strategy_result": {
                    "protocol": "followup.strategy.v1",
                    "customer_id": customer_id,
                    "strategy_level": "rescue",
                    "recommended_actions": [],
                    "recommended_action_count": 0,
                },
                "tool_name": "followup.plan_strategy",
                "customer_id": customer_id,
                "strategy_level": "rescue",
                "recommended_actions": [],
                "recommended_action_count": 0,
                "error": None,
            },
        )
        retry_response = client.post(f"/api/agent/runs/{run_id}/steps/{failed_step_id}/retry", headers=headers)
        assert retry_response.status_code == 200
        retry_data = retry_response.json()["data"]
        retry_run_id = retry_data["trace"]["run_id"]

        assert retry_run_id != run_id
        assert retry_data["retry"]["status"] == "succeeded"
        assert retry_data["retry"]["source_run_id"] == run_id
        assert retry_data["retry"]["new_run_id"] == retry_run_id
        assert retry_data["assistant_message"]["metadata_json"]["retry_source_step_id"] == failed_step_id
        assert retry_data["recovery_event"]["tool_name"] == "agent_chat.recovery_event"
        assert retry_data["recovery_event"]["metadata_json"]["source"] == "agent_step_retry"

        retry_detail_response = client.get(f"/api/agent/runs/{retry_run_id}", headers=headers)
        assert retry_detail_response.status_code == 200
        retry_detail = retry_detail_response.json()["data"]
        assert retry_detail["run"]["status"] == "success"
        assert len(retry_detail["steps"]) == 4
        assert retry_detail["steps"][1]["tool_name"] == "template_planner_v1"
        assert retry_detail["steps"][2]["tool_name"] == "agent_chat_tool_router_v1"
        assert retry_detail["steps"][3]["tool_name"] == "followup.plan_strategy"

        resume_response = client.post(f"/api/agent/runs/{run_id}/steps/{failed_step_id}/resume", headers=headers)
        assert resume_response.status_code == 200
        resume_data = resume_response.json()["data"]
        resume_run_id = resume_data["trace"]["run_id"]

        assert resume_data["resume"]["status"] == "succeeded"
        assert resume_data["resume"]["source_run_id"] == run_id
        assert resume_data["resume"]["new_run_id"] == resume_run_id
        assert resume_data["resume"]["resume_from_step"] == failed_step_id
        assert resume_data["assistant_message"]["metadata_json"]["resume_from_step"] == failed_step_id
        assert resume_data["recovery_event"]["metadata_json"]["source"] == "agent_partial_resume"
        assert resume_data["recovery_event"]["metadata_json"]["recovery_event"]["action"] == "partial_resume"

        source_detail_response = client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert source_detail_response.status_code == 200
        source_detail = source_detail_response.json()["data"]
        assert any(
            item["recovery_event"]["new_run_id"] == resume_run_id
            and item["recovery_event"]["resume_from_step"] == failed_step_id
            for item in source_detail["recovery_links"]
        )

        resume_detail_response = client.get(f"/api/agent/runs/{resume_run_id}", headers=headers)
        assert resume_detail_response.status_code == 200
        resume_detail = resume_detail_response.json()["data"]
        assert resume_detail["run"]["status"] == "success"
        assert any(item["recovery_event"]["source_run_id"] == run_id for item in resume_detail["recovery_links"])
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
        _cleanup_agent_runtime_trace(tenant_id, resume_run_id)
        _cleanup_agent_runtime_trace(tenant_id, retry_run_id)
        _cleanup_agent_runtime_trace(tenant_id, run_id)
        _cleanup_risk_chat_customer_fixture(tenant_id, customer_id, risk_snapshot_id)


def test_agent_chat_recovery_event_is_persisted_as_system_message():
    _ensure_agent_chat_tables_exist()
    client = TestClient(app)
    headers, tenant_id, _user_id = _build_headers(client)
    session_ids: list[str] = []

    try:
        create_response = client.post(
            "/api/agent/chat/sessions",
            headers=headers,
            json={
                "agent_scope": "general",
                "intent": "unknown",
                "title": "recovery event test",
            },
        )
        assert create_response.status_code == 200
        session_id = create_response.json()["data"]["session_id"]
        session_ids.append(session_id)

        event_response = client.post(
            f"/api/agent/chat/sessions/{session_id}/recovery-events",
            headers=headers,
            json={
                "action": "retry",
                "title": "Retry failed runtime",
                "status": "succeeded",
                "source_run_id": "run_failed_demo",
                "new_run_id": "run_retry_demo",
                "metadata_json": {"from_test": True},
            },
        )
        assert event_response.status_code == 200
        event_message = event_response.json()["data"]

        assert event_message["role"] == "system"
        assert event_message["tool_name"] == "agent_chat.recovery_event"
        assert event_message["run_id"] == "run_retry_demo"
        assert event_message["metadata_json"]["runtime_handler"] == "agent_chat.recovery_event"
        assert event_message["metadata_json"]["recovery_event"]["status"] == "succeeded"
        assert event_message["metadata_json"]["recovery_event"]["source_run_id"] == "run_failed_demo"
        assert event_message["metadata_json"]["from_test"] is True

        detail_response = client.get(f"/api/agent/chat/sessions/{session_id}", headers=headers)
        assert detail_response.status_code == 200
        detail_data = detail_response.json()["data"]
        messages = detail_data["messages"]
        assert messages[-1]["message_id"] == event_message["message_id"]
        assert messages[-1]["metadata_json"]["recovery_event"]["new_run_id"] == "run_retry_demo"
        assert detail_data["recovery_event_summary"]["total"] == 1
        assert detail_data["recovery_event_summary"]["succeeded_count"] == 1
        assert detail_data["recovery_event_summary"]["last_event"]["new_run_id"] == "run_retry_demo"

        list_response = client.get("/api/agent/chat/sessions?limit=20", headers=headers)
        assert list_response.status_code == 200
        listed_session = next(item for item in list_response.json()["data"] if item["session_id"] == session_id)
        assert listed_session["recovery_event_summary"]["total"] == 1
        assert listed_session["recovery_event_summary"]["last_event"]["status"] == "succeeded"

        succeeded_response = client.get("/api/agent/chat/sessions?recovery_status=succeeded&limit=20", headers=headers)
        assert succeeded_response.status_code == 200
        assert any(item["session_id"] == session_id for item in succeeded_response.json()["data"])

        failed_response = client.get("/api/agent/chat/sessions?recovery_status=failed&limit=20", headers=headers)
        assert failed_response.status_code == 200
        assert all(item["session_id"] != session_id for item in failed_response.json()["data"])

        events_response = client.get(f"/api/agent/chat/sessions/{session_id}/recovery-events", headers=headers)
        assert events_response.status_code == 200
        events = events_response.json()["data"]
        assert len(events) == 1
        assert events[0]["message_id"] == event_message["message_id"]
        assert events[0]["recovery_event"]["new_run_id"] == "run_retry_demo"

        stats_response = client.get("/api/agent/chat/recovery-events/stats", headers=headers)
        assert stats_response.status_code == 200
        stats = stats_response.json()["data"]
        assert stats["total_count"] >= 1
        assert stats["succeeded_count"] >= 1
        assert stats["success_rate"] >= 0
    finally:
        _cleanup_agent_chat_sessions(tenant_id, session_ids)
