from app.modules.system import router as system_router
from app.shared.event_bus import InMemoryEventBus


def test_event_bus_publish_subscribe_and_overview():
    bus = InMemoryEventBus()
    received: list[dict] = []
    bus.subscribe("agent.run.completed", received.append)

    event = bus.publish(
        tenant_id="tenant_event_a",
        event_type="agent.run.completed",
        source="agent_runtime",
        payload={"run_id": "run_event_001"},
        user_id="u_event",
        correlation_id="corr_event_001",
    )
    overview = bus.overview(tenant_id="tenant_event_a")

    assert event["event_type"] == "agent.run.completed"
    assert event["payload"]["run_id"] == "run_event_001"
    assert received[0]["event_id"] == event["event_id"]
    assert overview["event_bus_version"] == "event_bus_v1"
    assert overview["counts_by_type"]["agent.run.completed"] == 1
    assert overview["counts_by_source"]["agent_runtime"] == 1


def test_event_bus_list_events_isolated_by_tenant():
    bus = InMemoryEventBus()
    bus.publish(tenant_id="tenant_event_a", event_type="a.created", source="test", payload={})
    bus.publish(tenant_id="tenant_event_b", event_type="b.created", source="test", payload={})

    events = bus.list_events(tenant_id="tenant_event_a")

    assert len(events) == 1
    assert events[0]["tenant_id"] == "tenant_event_a"
    assert events[0]["event_type"] == "a.created"


def test_event_bus_overview_endpoint_uses_current_tenant(monkeypatch):
    bus = InMemoryEventBus()
    bus.publish(tenant_id="tenant_event_endpoint_a", event_type="agent.run.started", source="agent_runtime")
    bus.publish(tenant_id="tenant_event_endpoint_b", event_type="agent.run.started", source="agent_runtime")
    monkeypatch.setattr(system_router, "event_bus", bus)

    response = system_router.get_event_bus_overview(
        current_user={
            "tenant_id": "tenant_event_endpoint_a",
            "user_id": "u_admin",
            "permission_codes": ["system:rbac:manage"],
        }
    )

    assert response["total"] == 1
    assert response["data"]["event_bus_version"] == "event_bus_v1"
    assert response["data"]["latest_events"][0]["tenant_id"] == "tenant_event_endpoint_a"
