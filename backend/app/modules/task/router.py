from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.shared.response import success

router = APIRouter()


@router.get("")
def list_tasks(
    current_user: dict = Depends(require_permission("task:read:self")),
    db: Session = Depends(get_db),
):
    params = {"tenant_id": current_user["tenant_id"], "user_id": current_user["user_id"]}
    where_sql = "tenant_id = :tenant_id"
    if "task:read:team" not in current_user["permission_codes"] and "task:read:all" not in current_user["permission_codes"]:
        where_sql += " AND assignee_user_id = :user_id"

    rows = db.execute(
        text(
            f"""
            SELECT task_id, customer_id, assignee_user_id, task_type, title, priority,
                   status, due_at, created_at
            FROM sales_task
            WHERE {where_sql}
            ORDER BY due_at ASC, created_at DESC
            LIMIT 100
            """
        ),
        params,
    ).mappings().all()
    return success(list(rows), "查询成功", total=len(rows))
