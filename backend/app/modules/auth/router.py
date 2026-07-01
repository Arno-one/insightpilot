from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import LoginRequest
from app.shared.response import success

router = APIRouter()


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """账号密码登录，返回 JWT、角色和权限。"""
    user = db.execute(
        text(
            """
            SELECT tenant_id, user_id, username, real_name, password_hash, status, is_deleted
            FROM sys_user
            WHERE username = :username
            LIMIT 1
            """
        ),
        {"username": data.username},
    ).mappings().first()

    if not user or user["status"] != 1 or user["is_deleted"] != 0:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user["user_id"], user["username"], user["tenant_id"])
    # 中文注释：复用当前用户依赖的查询逻辑，确保登录返回的权限和接口校验一致。
    current_user = {
        "tenant_id": user["tenant_id"],
        "user_id": user["user_id"],
        "username": user["username"],
        "real_name": user["real_name"],
    }

    role_codes = db.execute(
        text(
            """
            SELECT r.role_code
            FROM sys_user_role ur
            JOIN sys_role r ON r.tenant_id = ur.tenant_id AND r.role_id = ur.role_id
            WHERE ur.tenant_id = :tenant_id AND ur.user_id = :user_id AND r.status = 1
            """
        ),
        current_user,
    ).scalars().all()

    permission_codes = db.execute(
        text(
            """
            SELECT DISTINCT p.permission_code
            FROM sys_user_role ur
            JOIN sys_role_permission rp ON rp.tenant_id = ur.tenant_id AND rp.role_id = ur.role_id
            JOIN sys_permission p ON p.permission_id = rp.permission_id
            WHERE ur.tenant_id = :tenant_id AND ur.user_id = :user_id AND p.status = 1
            """
        ),
        current_user,
    ).scalars().all()

    return success(
        {
            "token": token,
            "token_type": "bearer",
            "user": {
                **current_user,
                "role_codes": sorted(role_codes),
                "permission_codes": sorted(permission_codes),
            },
        },
        "登录成功",
    )


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return success(current_user, "查询成功")
