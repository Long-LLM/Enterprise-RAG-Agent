"""
Enterprise RAG Agent - FastAPI 主入口
"""
import sys
from contextlib import asynccontextmanager

from pathlib import Path

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, chunk_preview, conversation, document, health, permission, query, upload
from app.config import get_settings
from app.core.embedding import get_embedding_service
from app.core.llm import get_llm_service
from app.core.metrics import get_metrics_response, observe_http_request, CONTENT_TYPE
from app.core.milvus_store import get_milvus_store
from app.logger import get_logger, set_trace_id, LoggingMiddleware

settings = get_settings()
logger = get_logger("app.main")


# ---------- 生命周期管理 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期：
    - 启动：检查 Milvus 连接，初始化必要索引，创建默认管理员
    - 关闭：释放连接资源
    """
    logger.info("[START] RAG Agent 启动中...")

    # 初始化默认管理员账号
    try:
        from app.core.metadata_store import get_metadata_store
        store = await get_metadata_store()
        await store.init_default_admin()
    except Exception as e:
        logger.warning(f"默认管理员初始化失败（非关键）: {e}")

    logger.info("[START] RAG Agent 启动完成")

    yield

    # 关闭
    logger.info("[STOP] RAG Agent 关闭中...")
    try:
        from app.container import container
        await container.close_all()
    except Exception:
        pass
    logger.info("[OK] 资源已释放")


# ---------- FastAPI 实例 ----------
app = FastAPI(
    title="Enterprise RAG Agent",
    description="企业本地私有化 RAG Agent - 基于 FastAPI + Milvus + Ollama",
    version="0.1.0",
    lifespan=lifespan,
)

# Metrics 中间件：记录请求延迟和计数
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    observe_http_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration=duration,
    )
    return response

# 日志中间件（必须在 CORS 之前，确保 Trace ID 最早生成）
app.add_middleware(LoggingMiddleware)

# CORS（开发环境允许所有来源，生产环境需限制）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Metrics 端点 ----------
@app.get("/metrics")
async def metrics():
    """Prometheus 抓取端点"""
    return Response(content=get_metrics_response(), media_type=CONTENT_TYPE)


# ---------- 全局异常处理 ----------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    trace_id = set_trace_id()
    logger.bind(trace_id=trace_id, path=request.url.path).error(
        f"未捕获异常: {exc}", exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}",
            "trace_id": trace_id,
            "data": None,
        },
    )


# ---------- 路由注册 ----------
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(chunk_preview.router, prefix="/api")
app.include_router(document.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
app.include_router(permission.router, prefix="/api")
app.include_router(query.router, prefix="/api")


# ---------- 静态文件（前端 dist）----------
_frontend_dist = Path(__file__).parents[3] / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/")
    async def serve_index():
        return JSONResponse(
            content={
                "name": "Enterprise RAG Agent",
                "version": "0.1.0",
                "docs": "/docs",
                "health": "/api/health",
                "frontend": "请访问前端页面（如果配置了静态文件托管）",
            }
        )
else:
    @app.get("/")
    async def root():
        return {
            "name": "Enterprise RAG Agent",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/health",
        }


# ---------- 本地启动 ----------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
