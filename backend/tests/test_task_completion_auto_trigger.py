from app.modules.task import router as task_router


class _DummyJob:
    def __init__(self, job_id: str):
        self.id = job_id


class _DummyQueue:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def enqueue(self, job_name: str, *args, **kwargs):
        self.calls.append((job_name, args, kwargs))
        return _DummyJob(f"job_{len(self.calls)}")


def test_trigger_post_completion_jobs_submits_risk_and_report_jobs(monkeypatch):
    dummy_queue = _DummyQueue()
    monkeypatch.setattr(task_router, "get_default_queue", lambda: dummy_queue)

    result = task_router._trigger_post_completion_jobs(
        {"tenant_id": "demo_tenant", "user_id": "u_manager_001"},
        {"customer_id": "cust_demo_001"},
    )

    assert result["enqueue_status"] == "submitted"
    assert result["risk_scan_job_id"] == "job_1"
    assert result["daily_report_job_id"] == "job_2"
    assert dummy_queue.calls == [
        (
            "app.workers.risk_jobs.run_risk_scan",
            ("demo_tenant", "u_manager_001", "cust_demo_001"),
            {"job_timeout": 600},
        ),
        (
            "app.workers.report_jobs.generate_daily_report",
            ("demo_tenant", "u_manager_001"),
            {"job_timeout": 600},
        ),
    ]


def test_trigger_post_completion_jobs_does_not_raise_when_queue_fails(monkeypatch):
    def _raise_queue_error():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(task_router, "get_default_queue", _raise_queue_error)

    result = task_router._trigger_post_completion_jobs(
        {"tenant_id": "demo_tenant", "user_id": "u_manager_001"},
        {"customer_id": "cust_demo_001"},
    )

    assert result["enqueue_status"] == "failed"
    assert "redis unavailable" in result["error_message"]
