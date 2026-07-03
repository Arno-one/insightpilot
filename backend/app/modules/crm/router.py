from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.crm import service as crm_service
from app.modules.crm.import_service import build_template_csv, import_csv_file
from app.shared.response import success

router = APIRouter()


@router.get("/import/templates/{entity}.csv")
def download_import_template(
    entity: str,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
):
    """下载 CRM 导入模板，继续保持现有导入入口不变。"""
    file_name, csv_content = build_template_csv(entity)
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/import/{entity}")
async def import_crm_csv(
    entity: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """统一处理客户、商机、跟进记录三类 CSV 导入。"""
    result = await import_csv_file(entity, file, current_user, db)
    return success(result, "导入完成")


@router.get("/customers")
def list_customers(
    keyword: str | None = None,
    limit: int = 100,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """客户列表页复用统一服务层，后续内部工具和 MCP 也走同一套查询逻辑。"""
    rows = crm_service.search_customers(db, current_user, keyword=keyword, limit=limit)
    return success(rows, "查询成功", total=len(rows))


@router.get("/customers/{customer_id}")
def get_customer_detail(
    customer_id: str,
    risk_snapshot_id: str | None = None,
    current_user: dict = Depends(require_permission("crm:customer:read:self")),
    db: Session = Depends(get_db),
):
    """客户详情聚合接口，把风险、审批、任务和报告引用汇总到同一入口。"""
    detail = crm_service.load_customer_detail_bundle(
        db,
        current_user,
        customer_id,
        risk_snapshot_id=risk_snapshot_id,
    )
    return success(detail, "查询成功")
