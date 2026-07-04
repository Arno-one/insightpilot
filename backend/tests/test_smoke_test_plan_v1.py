from app.modules.system import router as system_router
from app.shared import smoke_test_plan
from scripts import print_smoke_test_plan


def test_smoke_test_plan_covers_required_pilot_modules():
    plan = smoke_test_plan.summarize_smoke_test_plan()
    modules = {step["module"] for step in plan["steps"]}

    assert plan["plan_version"] == "operational_smoke_test_plan_v1"
    assert plan["overall_status"] == "ready"
    assert plan["step_count"] == 8
    assert {"认证", "CRM", "Agent Trace", "NL2SQL", "RAG", "通知", "审批与任务", "系统健康"} == modules


def test_smoke_test_plan_keeps_execution_readonly():
    plan = smoke_test_plan.summarize_smoke_test_plan()
    boundary = plan["execution_boundary"]

    # 中文注释：冒烟计划只负责指导人工验证，不能在生成清单时执行业务接口或修改数据。
    assert boundary["auto_execute_enabled"] is False
    assert boundary["external_write_enabled"] is False
    assert boundary["data_mutation_enabled"] is False
    assert plan["operator_recording"]["mode"] == "frontend_draft_only"


def test_smoke_test_plan_declares_expected_evidence_for_every_step():
    plan = smoke_test_plan.summarize_smoke_test_plan()

    for step in plan["steps"]:
      assert step["expected_evidence"]
      assert step["rollback_hint"]
      assert step["side_effect_boundary"]


def test_system_smoke_test_plan_returns_protected_plan(monkeypatch):
    monkeypatch.setattr(
        system_router,
        "summarize_smoke_test_plan",
        lambda: {
            "plan_version": "operational_smoke_test_plan_v1",
            "overall_status": "ready",
            "step_count": 2,
            "steps": [],
        },
    )

    response = system_router.get_smoke_test_plan(
        current_user={"tenant_id": "demo_tenant", "user_id": "u_admin"}
    )

    assert response["code"] == 200
    assert response["data"]["plan_version"] == "operational_smoke_test_plan_v1"
    assert response["total"] == 2


def test_print_smoke_test_plan_script_exit_code(capsys):
    exit_code = print_smoke_test_plan.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"plan_version": "operational_smoke_test_plan_v1"' in output
    assert '"auto_execute_enabled": false' in output
