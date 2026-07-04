from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.agent_studio import service
from app.modules.agent_studio.schemas import AgentDefinitionCreateRequest
from app.modules.auth.dependencies import require_permission
from app.shared.response import success


router = APIRouter()


@router.get("/definitions")
def list_agent_definitions(
    status: str | None = None,
    limit: int = 50,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    rows = service.list_agent_definitions(db, current_user, status=status, limit=limit)
    return success(rows, "查询成功", total=len(rows))


@router.post("/definitions")
def create_agent_definition(
    body: AgentDefinitionCreateRequest,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    item = service.create_agent_definition(
        db,
        current_user,
        agent_code=body.agent_code,
        agent_name=body.agent_name,
        description=body.description,
        agent_type=body.agent_type,
        runtime_type=body.runtime_type,
        status=body.status,
        version=body.version,
        config_json=body.config_json,
        tool_policy_json=body.tool_policy_json,
        memory_policy_json=body.memory_policy_json,
    )
    return success(item, "Agent Definition 已创建")


@router.get("/definitions/{definition_id}")
def get_agent_definition(
    definition_id: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    try:
        item = service.get_agent_definition(db, current_user, definition_id=definition_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(item, "查询成功")
