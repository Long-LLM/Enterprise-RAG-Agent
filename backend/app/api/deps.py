"""
依赖注入（Dependency Injection）
统一管理各层服务的单例获取
"""
from app.core.chunking import get_chunking_engine
from app.core.embedding import get_embedding_service
from app.core.llm import get_llm_service
from app.core.metadata_store import get_metadata_store
from app.core.milvus_store import get_milvus_store
from app.core.parser import get_parser
from app.core.retrieval import get_hybrid_retriever
from app.core.reranker import get_reranker_service
from app.core.security import get_current_user, require_admin
from app.services.document_service import get_document_service
from app.services.rag_service import get_rag_service

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
