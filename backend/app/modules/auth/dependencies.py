from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import AuthError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """解析 JWT 并加载角色权限，后续接口和 Agent Tool 都基于这个上下文做权限判断。"""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    try:
        payload = decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = db.execute(
        text(
            """
            SELECT tenant_id, user_id, username, real_name, status, is_deleted
            FROM sys_user
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"tenant_id": payload["tenant_id"], "user_id": payload["sub"]},
    ).mappings().first()

    if not user or user["status"] != 1 or user["is_deleted"] != 0:
        raise HTTPException(status_code=401, detail="账号已失效，请重新登录")

    roles = db.execute(
        text(
            """
            SELECT r.role_code
            FROM sys_user_role ur
            JOIN sys_role r ON r.tenant_id = ur.tenant_id AND r.role_id = ur.role_id
            WHERE ur.tenant_id = :tenant_id AND ur.user_id = :user_id AND r.status = 1
            """
        ),
        {"tenant_id": user["tenant_id"], "user_id": user["user_id"]},
    ).scalars().all()

    permissions = db.execute(
        text(
            """
            SELECT DISTINCT p.permission_code
            FROM sys_user_role ur
            JOIN sys_role_permission rp ON rp.tenant_id = ur.tenant_id AND rp.role_id = ur.role_id
            JOIN sys_permission p ON p.permission_id = rp.permission_id
            WHERE ur.tenant_id = :tenant_id
              AND ur.user_id = :user_id
              AND p.status = 1
            """
        ),
        {"tenant_id": user["tenant_id"], "user_id": user["user_id"]},
    ).scalars().all()

    return {
        "tenant_id": user["tenant_id"],
        "user_id": user["user_id"],
        "username": user["username"],
        "real_name": user["real_name"],
        "role_codes": sorted(roles),
        "permission_codes": sorted(permissions),
    }


def require_permission(permission_code: str):
    def dependency(current_user: dict = Depends(get_current_user)):
        if permission_code not in current_user["permission_codes"]:
            raise HTTPException(status_code=403, detail=f"缺少权限: {permission_code}")
        return current_user

    return dependency
