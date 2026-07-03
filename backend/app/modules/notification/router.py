from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.notification import service as notification_service
from app.shared.response import success

router = APIRouter()


def _translate_notification_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/failed")
def list_failed_notifications(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        items = notification_service.list_failed_notification_deliveries(
            db,
            current_user=current_user,
            limit=limit,
        )
    except Exception as exc:  # pragma: no cover - 失败映射由下层服务测试间接覆盖
        raise _translate_notification_error(exc) from exc
    return success(items, "查询成功", total=len(items))


@router.get("/{notification_id}")
def get_notification_delivery_status(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = notification_service.get_notification_delivery_status(
            db,
            current_user=current_user,
            notification_id=notification_id,
        )
    except Exception as exc:  # pragma: no cover - 失败映射由下层服务测试间接覆盖
        raise _translate_notification_error(exc) from exc
    return success(result, "查询成功")


@router.post("/{notification_id}/retry")
def retry_notification_delivery(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = notification_service.retry_notification_delivery(
            db,
            current_user=current_user,
            notification_id=notification_id,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _translate_notification_error(exc) from exc
    return success(result, "邮件投递重试完成")
