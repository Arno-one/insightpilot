from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.memory import service
from app.modules.memory.schemas import LongTermMemorySearchRequest, MemoryGovernanceActionRequest
from app.shared.response import success

router = APIRouter()


@router.get("/overview")
def get_memory_system_overview(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.summarize_memory_system(db, current_user)
    return success(data, "查询成功")


@router.get("/short-term")
def list_short_term_memory_sessions(
    source_type: service.ShortTermSource | None = None,
    limit: int = 50,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    rows = service.list_short_term_sessions(db, current_user, source_type=source_type, limit=limit)
    return success(rows, "查询成功", total=len(rows))


@router.get("/short-term/summary")
def get_short_term_memory_summary(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    summary = service.summarize_short_term_memory(db, current_user)
    return success(summary, "查询成功", total=summary["session_count"])


@router.get("/short-term/{source_type}/{session_id}")
def get_short_term_memory_detail(
    source_type: service.ShortTermSource,
    session_id: str,
    limit: int = 100,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    try:
        data = service.load_short_term_memory(
            db,
            current_user,
            source_type=source_type,
            session_id=session_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(data, "查询成功", total=len(data["messages"]))


@router.get("/customers/{customer_id}/working")
def get_customer_working_memory(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.load_customer_working_memory(db, current_user, customer_id=customer_id)
    return success(data, "查询成功")


@router.get("/customers/{customer_id}/long-term")
def get_customer_long_term_memory(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.load_customer_long_term_memory(db, current_user, customer_id=customer_id)
    return success(data, "查询成功")


@router.post("/customers/{customer_id}/long-term/search")
def search_customer_long_term_memory(
    customer_id: str,
    body: LongTermMemorySearchRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.search_customer_long_term_memory(
        db,
        current_user,
        customer_id=customer_id,
        question=body.question,
        limit=body.limit,
        memory_types=body.memory_types,
        include_summary=body.include_summary,
        max_chars=body.max_chars,
    )
    return success(data, "检索成功", total=len(data["hits"]))


@router.get("/customers/{customer_id}/update-traces")
def list_customer_memory_update_traces(
    customer_id: str,
    limit: int = 50,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    rows = service.list_customer_memory_update_traces(db, current_user, customer_id=customer_id, limit=limit)
    return success(rows, "查询成功", total=len(rows))


@router.get("/customers/{customer_id}/context-packet")
def get_customer_context_packet(
    customer_id: str,
    max_chars: int = 2400,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.build_customer_context_packet(db, current_user, customer_id=customer_id, max_chars=max_chars)
    return success(data, "查询成功", total=len(data["sections"]))


@router.get("/customers/{customer_id}/governance")
def get_customer_memory_governance(
    customer_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.load_customer_memory_governance(db, current_user, customer_id=customer_id)
    return success(data, "查询成功")


@router.post("/customers/{customer_id}/governance/disable")
def disable_customer_memory(
    customer_id: str,
    body: MemoryGovernanceActionRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.update_customer_memory_governance(
        db,
        current_user,
        customer_id=customer_id,
        action="disable",
        reason=body.reason,
    )
    return success(data, "客户记忆已禁用")


@router.post("/customers/{customer_id}/governance/enable")
def enable_customer_memory(
    customer_id: str,
    body: MemoryGovernanceActionRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.update_customer_memory_governance(
        db,
        current_user,
        customer_id=customer_id,
        action="enable",
        reason=body.reason,
    )
    return success(data, "客户记忆已启用")


@router.post("/customers/{customer_id}/governance/request-refresh")
def request_customer_memory_refresh(
    customer_id: str,
    body: MemoryGovernanceActionRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.update_customer_memory_governance(
        db,
        current_user,
        customer_id=customer_id,
        action="request_refresh",
        reason=body.reason,
    )
    return success(data, "客户记忆刷新已请求")
