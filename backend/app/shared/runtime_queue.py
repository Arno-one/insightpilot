from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal

from app.shared.ids import new_id

RuntimeQueueStatus = Literal["queued", "running", "success", "failed"]


@dataclass(slots=True)
class RuntimeQueueItem:
    """中文注释：Runtime Queue V1 的内存任务结构，后续可映射到 Redis/Celery/数据库队列表。"""

    task_id: str
    tenant_id: str
    user_id: str
    task_type: str
    payload: dict[str, Any]
    status: RuntimeQueueStatus = "queued"
    run_id: str | None = None
    worker_id: str | None = None
    output_summary: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def model_dump(self) -> dict[str, Any]:
        item = asdict(self)
        for key in ["created_at", "started_at", "finished_at"]:
            value = item.get(key)
            item[key] = value.isoformat() if value else None
        return item


class InMemoryRuntimeQueue:
    """中文注释：V1 先提供进程内队列语义，不绑定外部队列服务，方便后续替换实现。"""

    def __init__(self):
        self._items: dict[str, RuntimeQueueItem] = {}
        self._lock = Lock()

    def enqueue(
        self,
        *,
        tenant_id: str,
        user_id: str,
        task_type: str,
        payload: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            item = RuntimeQueueItem(
                task_id=new_id("rtq"),
                tenant_id=tenant_id,
                user_id=user_id,
                task_type=task_type,
                payload=payload or {},
                run_id=run_id,
            )
            self._items[item.task_id] = item
            return item.model_dump()

    def start_next(self, *, tenant_id: str, worker_id: str) -> dict[str, Any] | None:
        with self._lock:
            queued_items = [
                item
                for item in self._items.values()
                if item.tenant_id == tenant_id and item.status == "queued"
            ]
            queued_items.sort(key=lambda item: item.created_at)
            if not queued_items:
                return None
            item = queued_items[0]
            item.status = "running"
            item.worker_id = worker_id
            item.started_at = datetime.now(UTC)
            return item.model_dump()

    def complete(self, task_id: str, *, output_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._finish(task_id, status="success", output_summary=output_summary, error_message=None)

    def fail(self, task_id: str, *, error_message: str) -> dict[str, Any]:
        return self._finish(task_id, status="failed", output_summary=None, error_message=error_message)

    def _finish(
        self,
        task_id: str,
        *,
        status: RuntimeQueueStatus,
        output_summary: dict[str, Any] | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            item = self._items.get(task_id)
            if not item:
                raise ValueError("Runtime Queue 任务不存在")
            item.status = status
            item.output_summary = output_summary
            item.error_message = error_message
            item.finished_at = datetime.now(UTC)
            return item.model_dump()

    def overview(self, *, tenant_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            items = [
                item
                for item in self._items.values()
                if tenant_id is None or item.tenant_id == tenant_id
            ]
            counts = {"queued": 0, "running": 0, "success": 0, "failed": 0}
            for item in items:
                counts[item.status] += 1
            latest_items = sorted(items, key=lambda item: item.created_at, reverse=True)[:20]
            return {
                "queue_version": "runtime_queue_v1",
                "backend": "in_memory",
                "task_count": len(items),
                "status_counts": counts,
                "latest_items": [item.model_dump() for item in latest_items],
            }


runtime_queue = InMemoryRuntimeQueue()
