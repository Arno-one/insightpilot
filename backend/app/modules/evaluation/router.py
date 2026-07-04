from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.evaluation import service
from app.modules.evaluation.schemas import EvaluationCaseCreateRequest, EvaluationDatasetCreateRequest
from app.shared.response import success

router = APIRouter()


@router.get("/datasets")
def list_evaluation_datasets(
    target_type: str | None = None,
    limit: int = 100,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    rows = service.list_datasets(db, tenant_id=current_user["tenant_id"], target_type=target_type, limit=limit)
    return success(rows, "查询成功", total=len(rows))


@router.post("/datasets")
def create_evaluation_dataset(
    data: EvaluationDatasetCreateRequest,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    item = service.create_dataset(
        db,
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        name=data.name,
        description=data.description,
        target_type=data.target_type,
        metadata_json=data.metadata_json,
    )
    return success(item, "创建成功")


@router.get("/cases")
def list_evaluation_cases(
    dataset_id: str | None = None,
    target_type: str | None = None,
    target_name: str | None = None,
    limit: int = 100,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    rows = service.list_cases(
        db,
        tenant_id=current_user["tenant_id"],
        dataset_id=dataset_id,
        target_type=target_type,
        target_name=target_name,
        limit=limit,
    )
    return success(rows, "查询成功", total=len(rows))


@router.post("/cases")
def create_evaluation_case(
    data: EvaluationCaseCreateRequest,
    current_user: dict = Depends(require_permission("agent:log:read")),
    db: Session = Depends(get_db),
):
    try:
        item = service.create_case(
            db,
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
            dataset_id=data.dataset_id,
            title=data.title,
            user_input=data.user_input,
            expected_behavior=data.expected_behavior,
            target_type=data.target_type,
            target_name=data.target_name,
            tags=data.tags,
            metadata_json=data.metadata_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success(item, "创建成功")
