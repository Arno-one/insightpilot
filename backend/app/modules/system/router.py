from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.system.schemas import UpdateRolePermissionsRequest, UpdateUserRolesRequest
from app.shared.audit_policy import summarize_audit_policy
from app.shared.backup_recovery import summarize_backup_recovery
from app.shared.deployment_readiness import summarize_deployment_readiness
from app.shared.enterprise_hardening import summarize_enterprise_hardening
from app.shared.event_bus import event_bus
from app.shared.response import success

router = APIRouter()

ADMIN_ROLE_CODE = "admin"
ADMIN_ROLE_ID = "role_admin"
SYSTEM_RBAC_PERMISSION = "system:rbac:manage"
SYSTEM_USER_ROLE_PERMISSION = "system:user_role:manage"


def _load_role(db: Session, tenant_id: str, role_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT role_id, role_code, role_name, status, remark
            FROM sys_role
            WHERE tenant_id = :tenant_id AND role_id = :role_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "role_id": role_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="角色不存在")
    return dict(row)


def _load_user(db: Session, tenant_id: str, user_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT user_id, username, real_name, status, is_deleted
            FROM sys_user
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return dict(row)


def _list_role_permission_codes(db: Session, tenant_id: str, role_id: str) -> list[str]:
    return db.execute(
        text(
            """
            SELECT p.permission_code
            FROM sys_role_permission rp
            JOIN sys_permission p ON p.permission_id = rp.permission_id
            WHERE rp.tenant_id = :tenant_id AND rp.role_id = :role_id AND p.status = 1
            ORDER BY p.module ASC, p.permission_code ASC
            """
        ),
        {"tenant_id": tenant_id, "role_id": role_id},
    ).scalars().all()


def _list_user_role_ids(db: Session, tenant_id: str, user_id: str) -> list[str]:
    return db.execute(
        text(
            """
            SELECT role_id
            FROM sys_user_role
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            ORDER BY role_id ASC
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    ).scalars().all()


def _ensure_permission_codes_exist(db: Session, permission_codes: list[str]) -> dict[str, str]:
    if not permission_codes:
        return {}

    permission_statement = text(
        """
        SELECT permission_id, permission_code
        FROM sys_permission
        WHERE permission_code IN :permission_codes AND status = 1
        """
    ).bindparams(bindparam("permission_codes", expanding=True))
    rows = db.execute(permission_statement, {"permission_codes": permission_codes}).mappings().all()
    mapping = {row["permission_code"]: row["permission_id"] for row in rows}
    missing_codes = [code for code in permission_codes if code not in mapping]
    if missing_codes:
        raise HTTPException(status_code=400, detail=f"存在无效权限编码: {', '.join(missing_codes)}")
    return mapping


def _ensure_role_ids_exist(db: Session, tenant_id: str, role_ids: list[str]) -> dict[str, dict]:
    role_statement = text(
        """
        SELECT role_id, role_code, role_name
        FROM sys_role
        WHERE tenant_id = :tenant_id AND role_id IN :role_ids AND status = 1
        """
    ).bindparams(bindparam("role_ids", expanding=True))
    rows = db.execute(role_statement, {"tenant_id": tenant_id, "role_ids": role_ids}).mappings().all()
    mapping = {row["role_id"]: dict(row) for row in rows}
    missing_ids = [role_id for role_id in role_ids if role_id not in mapping]
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"存在无效角色 ID: {', '.join(missing_ids)}")
    return mapping


def _ensure_admin_role_keeps_system_permissions(role: dict, permission_codes: list[str]):
    # 中文注释：admin 是系统治理入口，至少要保留权限管理和用户角色管理两类能力。
    if role["role_code"] != ADMIN_ROLE_CODE:
        return

    required_permissions = {SYSTEM_RBAC_PERMISSION, SYSTEM_USER_ROLE_PERMISSION}
    if not required_permissions.issubset(set(permission_codes)):
        raise HTTPException(status_code=400, detail="admin 角色必须保留系统权限管理与用户角色管理权限")


def _ensure_not_remove_last_admin(db: Session, tenant_id: str, user_id: str, next_role_ids: list[str]):
    # 中文注释：至少保留一个 admin，避免最后一个系统管理员被误删后无人能再改权限。
    current_role_ids = set(_list_user_role_ids(db, tenant_id, user_id))
    removing_admin_role = ADMIN_ROLE_ID in current_role_ids and ADMIN_ROLE_ID not in set(next_role_ids)
    if not removing_admin_role:
        return

    admin_user_count = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM sys_user_role
            WHERE tenant_id = :tenant_id AND role_id = :role_id
            """
        ),
        {"tenant_id": tenant_id, "role_id": ADMIN_ROLE_ID},
    ).scalar_one()
    if admin_user_count <= 1:
        raise HTTPException(status_code=400, detail="系统中至少需要保留一个 admin 账号")


def _derive_team_scope(role_codes: list[str], permission_codes: list[str]) -> str:
    """中文注释：Org / Team V1 先从角色和权限推导团队层级，后续可平滑替换为组织表。"""
    role_set = set(role_codes)
    permission_set = set(permission_codes)
    if {"admin", "owner"} & role_set or "crm:customer:read:all" in permission_set:
        return "tenant_admin"
    if "manager" in role_set or "crm:customer:read:team" in permission_set:
        return "team_manager"
    if "salesperson" in role_set or "crm:customer:read:self" in permission_set:
        return "team_member"
    return "limited_member"


def _derive_crm_visibility(permission_codes: list[str]) -> str:
    permission_set = set(permission_codes)
    if "crm:customer:read:all" in permission_set:
        return "all"
    if "crm:customer:read:team" in permission_set:
        return "team"
    if "crm:customer:read:self" in permission_set:
        return "self"
    return "none"


def _list_user_permission_codes(db: Session, tenant_id: str, user_id: str) -> list[str]:
    return db.execute(
        text(
            """
            SELECT DISTINCT p.permission_code
            FROM sys_user_role ur
            JOIN sys_role_permission rp ON rp.tenant_id = ur.tenant_id AND rp.role_id = ur.role_id
            JOIN sys_permission p ON p.permission_id = rp.permission_id
            WHERE ur.tenant_id = :tenant_id
              AND ur.user_id = :user_id
              AND p.status = 1
            ORDER BY p.permission_code ASC
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    ).scalars().all()


@router.get("/team-model")
def get_team_model(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
    db: Session = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    user_rows = db.execute(
        text(
            """
            SELECT user_id, username, real_name, status
            FROM sys_user
            WHERE tenant_id = :tenant_id AND is_deleted = 0
            ORDER BY username ASC
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()

    users = []
    scope_counts: dict[str, int] = {}
    for row in user_rows:
        user = dict(row)
        role_links = db.execute(
            text(
                """
                SELECT r.role_id, r.role_code, r.role_name
                FROM sys_user_role ur
                JOIN sys_role r ON r.tenant_id = ur.tenant_id AND r.role_id = ur.role_id
                WHERE ur.tenant_id = :tenant_id AND ur.user_id = :user_id AND r.status = 1
                ORDER BY r.role_code ASC
                """
            ),
            {"tenant_id": tenant_id, "user_id": user["user_id"]},
        ).mappings().all()
        role_codes = [item["role_code"] for item in role_links]
        permission_codes = _list_user_permission_codes(db, tenant_id, user["user_id"])
        team_scope = _derive_team_scope(role_codes, permission_codes)
        scope_counts[team_scope] = scope_counts.get(team_scope, 0) + 1
        users.append(
            {
                **user,
                "role_ids": [item["role_id"] for item in role_links],
                "role_codes": role_codes,
                "role_names": [item["role_name"] for item in role_links],
                "permission_codes": permission_codes,
                "team_scope": team_scope,
                "crm_visibility": _derive_crm_visibility(permission_codes),
                "can_manage_team": "crm:customer:read:team" in permission_codes,
                "can_review_approval": "approval:review:agent_task" in permission_codes,
                "can_manage_system": SYSTEM_RBAC_PERMISSION in permission_codes,
            }
        )

    return success(
        {
            "model_version": "org_team_model_v1",
            "tenant_id": tenant_id,
            "user_count": len(users),
            "scope_counts": scope_counts,
            "users": users,
        },
        "查询成功",
        total=len(users),
    )


@router.get("/audit-policy")
def get_audit_policy(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
):
    """中文注释：只读输出平台审计策略，后续可替换为数据库配置。"""
    _ = current_user
    policy = summarize_audit_policy()
    return success(policy, "查询成功", total=policy["rule_count"])


@router.get("/event-bus/overview")
def get_event_bus_overview(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
):
    """中文注释：只读输出内部事件总线概览，V1 不依赖外部消息中间件。"""
    overview = event_bus.overview(tenant_id=current_user["tenant_id"])
    return success(overview, "查询成功", total=overview["event_count"])


@router.get("/deployment-readiness")
def get_deployment_readiness(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
):
    """中文注释：受 RBAC 保护的部署体检详情，只输出脱敏配置状态和风险建议。"""
    _ = current_user
    readiness = summarize_deployment_readiness(public=False)
    return success(readiness, "查询成功", total=sum(readiness["check_counts"].values()))


@router.get("/backup-recovery")
def get_backup_recovery(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
):
    """中文注释：输出备份恢复策略和演练步骤，不触发真实备份或恢复动作。"""
    _ = current_user
    plan = summarize_backup_recovery()
    return success(plan, "查询成功", total=plan["domain_count"])


@router.get("/enterprise-hardening")
def get_enterprise_hardening(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
):
    """中文注释：企业级硬化阶段总览，聚合部署、审计、队列、事件、备份恢复等只读状态。"""
    report = summarize_enterprise_hardening(tenant_id=current_user["tenant_id"])
    return success(report, "查询成功", total=report["control_count"])


@router.get("/access-control")
def get_access_control_data(
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
    db: Session = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    permission_rows = db.execute(
        text(
            """
            SELECT permission_id, permission_code, permission_name, module, action, description
            FROM sys_permission
            WHERE status = 1
            ORDER BY module ASC, permission_code ASC
            """
        )
    ).mappings().all()
    permissions = [dict(row) for row in permission_rows]

    role_rows = db.execute(
        text(
            """
            SELECT role_id, role_code, role_name, status, remark
            FROM sys_role
            WHERE tenant_id = :tenant_id AND status = 1
            ORDER BY role_code ASC
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    roles = []
    for row in role_rows:
        role = dict(row)
        role["permission_codes"] = _list_role_permission_codes(db, tenant_id, role["role_id"])
        roles.append(role)

    user_rows = db.execute(
        text(
            """
            SELECT user_id, username, real_name, status
            FROM sys_user
            WHERE tenant_id = :tenant_id AND is_deleted = 0
            ORDER BY username ASC
            """
        ),
        {"tenant_id": tenant_id},
    ).mappings().all()
    users = []
    for row in user_rows:
        user = dict(row)
        role_links = db.execute(
            text(
                """
                SELECT r.role_id, r.role_code, r.role_name
                FROM sys_user_role ur
                JOIN sys_role r ON r.tenant_id = ur.tenant_id AND r.role_id = ur.role_id
                WHERE ur.tenant_id = :tenant_id AND ur.user_id = :user_id AND r.status = 1
                ORDER BY r.role_code ASC
                """
            ),
            {"tenant_id": tenant_id, "user_id": user["user_id"]},
        ).mappings().all()
        user["role_ids"] = [item["role_id"] for item in role_links]
        user["role_codes"] = [item["role_code"] for item in role_links]
        user["role_names"] = [item["role_name"] for item in role_links]
        users.append(user)

    return success(
        {
            "roles": roles,
            "permissions": permissions,
            "users": users,
        },
        "查询成功",
        total=len(roles),
    )


@router.patch("/roles/{role_id}/permissions")
def update_role_permissions(
    role_id: str,
    data: UpdateRolePermissionsRequest,
    current_user: dict = Depends(require_permission(SYSTEM_RBAC_PERMISSION)),
    db: Session = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    role = _load_role(db, tenant_id, role_id)
    permission_codes = list(dict.fromkeys(data.permission_codes))
    _ensure_admin_role_keeps_system_permissions(role, permission_codes)
    permission_map = _ensure_permission_codes_exist(db, permission_codes)

    db.execute(
        text(
            """
            DELETE FROM sys_role_permission
            WHERE tenant_id = :tenant_id AND role_id = :role_id
            """
        ),
        {"tenant_id": tenant_id, "role_id": role_id},
    )

    if permission_codes:
        db.execute(
            text(
                """
                INSERT INTO sys_role_permission (tenant_id, role_id, permission_id)
                VALUES (:tenant_id, :role_id, :permission_id)
                """
            ),
            [
                {
                    "tenant_id": tenant_id,
                    "role_id": role_id,
                    "permission_id": permission_map[permission_code],
                }
                for permission_code in permission_codes
            ],
        )

    db.commit()
    return success(
        {
            "role_id": role_id,
            "role_code": role["role_code"],
            "permission_codes": permission_codes,
        },
        "角色权限已更新",
    )


@router.patch("/users/{user_id}/roles")
def update_user_roles(
    user_id: str,
    data: UpdateUserRolesRequest,
    current_user: dict = Depends(require_permission(SYSTEM_USER_ROLE_PERMISSION)),
    db: Session = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    _load_user(db, tenant_id, user_id)
    role_ids = list(dict.fromkeys(data.role_ids))
    _ensure_role_ids_exist(db, tenant_id, role_ids)
    _ensure_not_remove_last_admin(db, tenant_id, user_id, role_ids)

    db.execute(
        text(
            """
            DELETE FROM sys_user_role
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            """
        ),
        {"tenant_id": tenant_id, "user_id": user_id},
    )
    db.execute(
        text(
            """
            INSERT INTO sys_user_role (tenant_id, user_id, role_id)
            VALUES (:tenant_id, :user_id, :role_id)
            """
        ),
        [{"tenant_id": tenant_id, "user_id": user_id, "role_id": role_id} for role_id in role_ids],
    )
    db.commit()

    return success(
        {
            "user_id": user_id,
            "role_ids": role_ids,
        },
        "用户角色已更新",
    )
