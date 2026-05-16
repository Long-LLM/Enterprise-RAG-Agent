"""
健康检查与系统状态接口
"""
import httpx
from fastapi import APIRouter

from app.config import get_settings
from app.models.schemas import HealthCheckResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """系统健康检查 — 每次都新建连接探测，避免缓存失效状态"""
    settings = get_settings()

    # Milvus 连接检查（直接新建连接探测）
    milvus_ok = False
    try:
        from pymilvus import MilvusClient
        client = MilvusClient(
            uri=settings.milvus_uri,
            token=settings.MILVUS_TOKEN or None,
            db_name=settings.MILVUS_DB_NAME,
            timeout=5,
        )
        client.get_server_version()
        milvus_ok = True
        client.close()
    except Exception:
        milvus_ok = False

    # Ollama / LLM 检查（直接 HTTP 探测）
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", m.get("model", "")) for m in models]
                embed_found = any(settings.OLLAMA_EMBED_MODEL in name for name in model_names)
                llm_found = any(settings.OLLAMA_LLM_MODEL in name for name in model_names)
                ollama_ok = embed_found and llm_found
    except Exception:
        ollama_ok = False

    return HealthCheckResponse(
        data=HealthCheckResponse.HealthData(
            status="healthy" if (milvus_ok and ollama_ok) else "degraded",
            milvus_connected=milvus_ok,
            ollama_connected=ollama_ok,
            llm_provider=settings.LLM_PROVIDER,
        )
    )
