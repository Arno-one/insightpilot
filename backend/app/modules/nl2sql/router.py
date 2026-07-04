from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db, get_readonly_db
from app.modules.auth.dependencies import require_permission
from app.modules.nl2sql import service
from app.modules.nl2sql.schemas import (
    NL2SQLMessageCreateRequest,
    NL2SQLQueryAuditCreateRequest,
    NL2SQLQueryRequest,
    NL2SQLSessionCreateRequest,
)
from app.shared.response import success


router = APIRouter()


def _translate_not_found(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.post("/sessions")
def create_nl2sql_session(
    body: NL2SQLSessionCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.create_session(
        db,
        current_user,
        title=body.title,
        data_scope=body.data_scope,
        context_json=body.context_json,
    )
    return success(data, "NL2SQL 会话已创建")


@router.get("/sessions")
def list_nl2sql_sessions(
    status: str = "active",
    limit: int = 50,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    data = service.list_sessions(db, current_user, status=status, limit=limit)
    return success(data, "查询成功", total=len(data))


@router.get("/sessions/{session_id}")
def get_nl2sql_session_detail(
    session_id: str,
    limit: int = 100,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    try:
        data = service.load_session_detail(db, current_user, session_id=session_id, limit=limit)
    except ValueError as exc:
        raise _translate_not_found(exc) from exc
    return success(data, "查询成功", total=len(data["messages"]))


@router.post("/sessions/{session_id}/messages")
def append_nl2sql_message(
    session_id: str,
    body: NL2SQLMessageCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    try:
        data = service.append_message(
            db,
            current_user,
            session_id=session_id,
            role=body.role,
            content=body.content,
            query_id=body.query_id,
            metadata_json=body.metadata_json,
        )
    except ValueError as exc:
        raise _translate_not_found(exc) from exc
    return success(data, "NL2SQL 消息已写入")


@router.post("/query-audits")
def create_nl2sql_query_audit(
    body: NL2SQLQueryAuditCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    try:
        data = service.create_query_audit(db, current_user, session_id=body.session_id, question=body.question)
    except ValueError as exc:
        raise _translate_not_found(exc) from exc
    return success(data, "NL2SQL 查询审计已创建")


@router.post("/query")
def query_nl2sql(
    body: NL2SQLQueryRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
    readonly_db: Session = Depends(get_readonly_db),
):
    try:
        data = service.query(db, readonly_db, current_user, question=body.question, session_id=body.session_id)
    except ValueError as exc:
        raise _translate_not_found(exc) from exc
    return success(data, "NL2SQL 查询完成")
