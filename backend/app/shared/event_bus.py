from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

from app.shared.ids import new_id

UTC = timezone.utc

EventHandler = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class EventBusRecord:
    """中文注释：内部事件总线记录，V1 先用于进程内发布和观测。"""

    event_id: str
    tenant_id: str
    event_type: str
    source: str
    payload: dict[str, Any]
    user_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def model_dump(self) -> dict[str, Any]:
        item = asdict(self)
        item["created_at"] = self.created_at.isoformat()
        return item


class InMemoryEventBus:
    """中文注释：Event Bus V1 的进程内实现，先统一事件语义，后续再替换外部中间件。"""

    def __init__(self):
        self._events: list[EventBusRecord] = []
        self._handlers: dict[str, list[EventHandler]] = {}
        self._lock = Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def publish(
        self,
        *,
        tenant_id: str,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = EventBusRecord(
                event_id=new_id("evtbus"),
                tenant_id=tenant_id,
                event_type=event_type,
                source=source,
                payload=payload or {},
                user_id=user_id,
                correlation_id=correlation_id,
            )
            self._events.append(record)
            handlers = list(self._handlers.get(event_type, []))
            payload_for_handlers = record.model_dump()
        for handler in handlers:
            handler(payload_for_handlers)
        return payload_for_handlers

    def list_events(self, *, tenant_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._lock:
            events = [
                event
                for event in self._events
                if tenant_id is None or event.tenant_id == tenant_id
            ]
            events.sort(key=lambda event: event.created_at, reverse=True)
            return [event.model_dump() for event in events[:safe_limit]]

    def overview(self, *, tenant_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            events = [
                event
                for event in self._events
                if tenant_id is None or event.tenant_id == tenant_id
            ]
            counts_by_type: dict[str, int] = {}
            counts_by_source: dict[str, int] = {}
            for event in events:
                counts_by_type[event.event_type] = counts_by_type.get(event.event_type, 0) + 1
                counts_by_source[event.source] = counts_by_source.get(event.source, 0) + 1
        return {
            "event_bus_version": "event_bus_v1",
            "backend": "in_memory",
            "event_count": len(events),
            "counts_by_type": counts_by_type,
            "counts_by_source": counts_by_source,
            "latest_events": self.list_events(tenant_id=tenant_id, limit=20),
        }


event_bus = InMemoryEventBus()
