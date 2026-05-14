"""
健康检查与系统状态接口
"""
from fastapi import APIRouter

from app.api.deps import get_embedding_service, get_llm_service, get_milvus_store
from app.config import get_settings
from app.models.schemas import HealthCheckResponse

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """系统健康检查"""
    milvus = get_milvus_store()
    embed = get_embedding_service()
    llm = get_llm_service()
    settings = get_settings()

    milvus_ok = milvus.health_check()
    ollama_ok = await embed.health_check() and await llm.health_check()

    return HealthCheckResponse(
        data=HealthCheckResponse.HealthData(
            status="healthy" if (milvus_ok and ollama_ok) else "degraded",
            milvus_connected=milvus_ok,
            ollama_connected=ollama_ok,
            llm_provider=settings.LLM_PROVIDER,
        )
    )
