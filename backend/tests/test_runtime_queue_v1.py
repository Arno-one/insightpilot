from app.modules.agent import router as agent_router
from app.shared.runtime_queue import InMemoryRuntimeQueue


def test_runtime_queue_tracks_lifecycle_and_tenant_isolation():
    queue = InMemoryRuntimeQueue()

    first = queue.enqueue(
        tenant_id="tenant_queue_a",
        user_id="user_queue_a",
        task_type="agent.long_task",
        payload={"question": "生成报告"},
    )
    queue.enqueue(
        tenant_id="tenant_queue_b",
        user_id="user_queue_b",
        task_type="agent.long_task",
        payload={"question": "跨租户任务"},
    )

    running = queue.start_next(tenant_id="tenant_queue_a", worker_id="worker_001")
    completed = queue.complete(first["task_id"], output_summary={"status": "ok"})
    overview_a = queue.overview(tenant_id="tenant_queue_a")
    overview_b = queue.overview(tenant_id="tenant_queue_b")

    assert running["task_id"] == first["task_id"]
    assert running["status"] == "running"
    assert completed["status"] == "success"
    assert completed["output_summary"] == {"status": "ok"}
    assert overview_a["status_counts"]["success"] == 1
    assert overview_a["task_count"] == 1
    assert overview_b["status_counts"]["queued"] == 1
    assert overview_b["task_count"] == 1


def test_runtime_queue_can_mark_failed_task():
    queue = InMemoryRuntimeQueue()
    item = queue.enqueue(
        tenant_id="tenant_queue_fail",
        user_id="user_queue_fail",
        task_type="agent.failed_task",
    )

    failed = queue.fail(item["task_id"], error_message="执行失败")

    assert failed["status"] == "failed"
    assert failed["error_message"] == "执行失败"
    assert queue.overview(tenant_id="tenant_queue_fail")["status_counts"]["failed"] == 1


def test_runtime_queue_overview_endpoint_uses_current_tenant(monkeypatch):
    queue = InMemoryRuntimeQueue()
    queue.enqueue(tenant_id="tenant_endpoint_a", user_id="u_a", task_type="agent.task")
    queue.enqueue(tenant_id="tenant_endpoint_b", user_id="u_b", task_type="agent.task")
    monkeypatch.setattr(agent_router, "runtime_queue", queue)

    response = agent_router.get_runtime_queue_overview(
        current_user={
            "tenant_id": "tenant_endpoint_a",
            "user_id": "u_a",
            "permission_codes": ["agent:log:read"],
        }
    )

    assert response["total"] == 1
    assert response["data"]["queue_version"] == "runtime_queue_v1"
    assert response["data"]["backend"] == "in_memory"
    assert response["data"]["latest_items"][0]["tenant_id"] == "tenant_endpoint_a"
