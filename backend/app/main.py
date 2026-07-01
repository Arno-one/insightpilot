from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.modules.auth.router import router as auth_router
from app.modules.crm.router import router as crm_router
from app.modules.risk.router import router as risk_router
from app.modules.approval.router import router as approval_router
from app.modules.task.router import router as task_router
from app.modules.report.router import router as report_router
from app.modules.agent.router import router as agent_router
from app.modules.rag.router import router as rag_router


def create_app() -> FastAPI:
    """创建 FastAPI 应用，V1 使用模块化单体，后期可按模块拆服务。"""
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="面向中小企业的 AI 企业运营参谋系统",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix="/api/auth", tags=["认证与权限"])
    app.include_router(crm_router, prefix="/api/crm", tags=["CRM"])
    app.include_router(risk_router, prefix="/api/risk", tags=["风险分析"])
    app.include_router(approval_router, prefix="/api/approvals", tags=["人工审批"])
    app.include_router(task_router, prefix="/api/tasks", tags=["销售任务"])
    app.include_router(report_router, prefix="/api/reports", tags=["经营报告"])
    app.include_router(agent_router, prefix="/api/agent", tags=["Agent执行追踪"])
    app.include_router(rag_router, prefix="/api/rag", tags=["RAG知识库"])

    @app.get("/health")
    def health():
        return {"code": 200, "msg": "success", "data": {"status": "ok"}, "total": None}

    return app


app = create_app()
