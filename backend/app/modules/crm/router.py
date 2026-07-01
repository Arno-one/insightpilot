from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.shared.response import success

router = APIRouter()


@router.get("/customers")
def list_customers(
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """客户列表；V1 先按角色决定数据范围，后续可下沉到策略对象。"""
    params = {"tenant_id": current_user["tenant_id"], "user_id": current_user["user_id"]}
    if "crm:customer:read:all" in current_user["permission_codes"]:
        where_sql = "tenant_id = :tenant_id"
    elif "crm:customer:read:team" in current_user["permission_codes"]:
        where_sql = "tenant_id = :tenant_id"
    else:
        where_sql = "tenant_id = :tenant_id AND owner_user_id = :user_id"

    rows = db.execute(
        text(
            f"""
            SELECT customer_id, customer_name, owner_user_id, lifecycle_stage, intent_level,
                   customer_level, competitor_involved, last_follow_up_at, next_follow_up_at
            FROM crm_customer
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT 100
            """
        ),
        params,
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))
