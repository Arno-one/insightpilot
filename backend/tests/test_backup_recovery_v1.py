from datetime import UTC, datetime

from app.modules.system import router as system_router
from app.shared import backup_recovery
from scripts import print_backup_recovery_plan


def test_backup_recovery_covers_enterprise_critical_tables():
    plan = backup_recovery.summarize_backup_recovery(generated_at=datetime(2026, 7, 4, tzinfo=UTC))
    tables = {table for domain in plan["manifest"]["domains"] for table in domain["tables"]}

    assert plan["plan_version"] == "backup_recovery_v1"
    assert plan["overall_status"] == "ready"
    assert plan["check_counts"]["fail"] == 0
    # 中文注释：这些表代表租户、权限、核心业务、Agent 轨迹和知识库，漏掉任一类都会影响企业级恢复。
    assert {
        "tenant",
        "sys_user",
        "crm_customer",
        "approval_record",
        "agent_run",
        "agent_chat_message",
        "nl2sql_query_audit",
        "customer_memory",
        "rag_document",
        "agent_definition",
        "business_report",
    }.issubset(tables)


def test_backup_recovery_restore_order_is_deterministic():
    domains = backup_recovery.list_backup_domains()
    restore_orders = [domain["restore_order"] for domain in domains]

    assert restore_orders == sorted(restore_orders)
    assert len(restore_orders) == len(set(restore_orders))
    assert domains[0]["domain_id"] == "tenant_identity"


def test_backup_recovery_blocks_automatic_destructive_restore():
    plan = backup_recovery.summarize_backup_recovery()
    guardrail_ids = {item["guardrail_id"] for item in plan["guardrails"]}

    assert plan["execution_boundary"]["auto_restore_enabled"] is False
    assert plan["execution_boundary"]["external_write_enabled"] is False
    assert {"manual_approval_required", "dry_run_first", "tenant_scope_lock"}.issubset(guardrail_ids)


def test_system_backup_recovery_returns_protected_plan(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_backup_recovery",
        lambda: {
            "plan_version": "backup_recovery_v1",
            "overall_status": "ready",
            "domain_count": 2,
            "table_count": 5,
            "check_counts": {"pass": 1, "warn": 1, "fail": 0},
        },
    )

    response = system_router.get_backup_recovery(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"}
    )

    assert response["code"] == 200
    assert response["data"]["plan_version"] == "backup_recovery_v1"
    assert response["total"] == 2


def test_print_backup_recovery_plan_script_is_readonly(capsys):
    exit_code = print_backup_recovery_plan.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"plan_version": "backup_recovery_v1"' in output
    assert '"auto_restore_enabled": false' in output
