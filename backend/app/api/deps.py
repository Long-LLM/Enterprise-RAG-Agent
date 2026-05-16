"""
依赖注入（Dependency Injection）
统一管理各层服务的单例获取

迁移中：从模块级全局单例逐步迁移到 app.container 统一注册表
"""
from app.container import (
    get_chunking_engine,
    get_document_service,
    get_embedding_service,
    get_hybrid_retriever,
    get_llm_service,
    get_milvus_store,
    get_parser,
    get_rag_service,
    get_reranker_service,
)
from app.core.metadata_store import get_metadata_store
from app.core.security import get_current_user, require_admin

__all__ = [
    "get_milvus_store",
    "get_embedding_service",
    "get_llm_service",
    "get_parser",
    "get_chunking_engine",
    "get_hybrid_retriever",
    "get_reranker_service",
    "get_document_service",
    "get_rag_service",
    "get_metadata_store",
    "get_current_user",
    "require_admin",
]
