"""
依赖注入容器 (DI Container)

目标：
1. 统一管理核心服务的生命周期
2. 支持测试时覆盖(mock)
3. 兼容 FastAPI Depends
4. 渐进式替换全局单例

使用方式：
    # 在路由中使用
    from app.container import get_milvus_store, get_rag_service

    @router.get("/docs")
    async def list_docs(
        milvus: MilvusStore = Depends(get_milvus_store),
        service: DocumentService = Depends(get_document_service),
    ):
        ...

    # 在测试中覆盖
    from app.container import container
    container.override(MilvusStore, mock_milvus)
"""
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from fastapi import Request

T = TypeVar("T")


class ServiceContainer:
    """
    轻量级服务容器
    - 注册：服务类型 -> 工厂函数
    - 解析：按需创建或返回已有实例
    - 覆盖：测试时替换实现
    - 清理：应用关闭时释放资源
    """

    def __init__(self):
        self._registry: Dict[Type, Callable[[], Any]] = {}
        self._singletons: Dict[Type, Any] = {}
        self._overrides: Dict[Type, Any] = {}

    def register(self, interface: Type[T], factory: Callable[[], T], singleton: bool = True):
        """
        注册服务
        :param interface: 服务接口/类型（用于查找）
        :param factory: 工厂函数，返回服务实例
        :param singleton: 是否单例（默认 True）
        """
        self._registry[interface] = (factory, singleton)

    def resolve(self, interface: Type[T]) -> T:
        """
        解析服务实例
        优先级：覆盖 > 已有单例 > 工厂创建
        """
        # 1. 测试覆盖
        if interface in self._overrides:
            return self._overrides[interface]

        # 2. 已有单例
        if interface in self._singletons:
            return self._singletons[interface]

        # 3. 工厂创建
        if interface not in self._registry:
            raise KeyError(f"服务未注册: {interface.__name__}")

        factory, singleton = self._registry[interface]
        instance = factory()

        if singleton:
            self._singletons[interface] = instance

        return instance

    def override(self, interface: Type[T], instance: T):
        """测试/开发时覆盖服务实现"""
        self._overrides[interface] = instance

    def reset_override(self, interface: Optional[Type] = None):
        """清除覆盖"""
        if interface is None:
            self._overrides.clear()
        else:
            self._overrides.pop(interface, None)

    def clear_singletons(self):
        """清除所有单例实例（用于测试隔离）"""
        self._singletons.clear()

    async def close_all(self):
        """关闭所有持有资源的服务"""
        for interface, instance in list(self._singletons.items()):
            if hasattr(instance, "close"):
                try:
                    if hasattr(instance.close, "__await__"):
                        await instance.close()
                    else:
                        instance.close()
                except Exception:
                    pass
            if hasattr(instance, "aclose"):
                try:
                    await instance.aclose()
                except Exception:
                    pass
        self._singletons.clear()


# 全局容器实例
container = ServiceContainer()


# ========================== FastAPI Depends 适配器 ==========================

def get_from_container(interface: Type[T]) -> Callable[[Request], T]:
    """
    生成 FastAPI Depends 函数
    用法: Depends(get_from_container(MyService))
    """
    def _resolver(request: Request) -> T:
        return container.resolve(interface)
    return _resolver


# ========================== 延迟导入避免循环依赖 ==========================

def _lazy_register_all():
    """注册所有核心服务（延迟导入，避免启动时循环依赖）"""
    from app.config import get_settings
    from app.core.chunking import ChunkingEngine
    from app.core.embedding import EmbeddingService
    from app.core.llm import LLMService
    from app.core.milvus_store import MilvusStore
    from app.core.parser import DocumentParser
    from app.core.retrieval import HybridRetriever
    from app.core.reranker import RerankerService
    from app.services.document_service import DocumentService
    from app.services.rag_service import RAGService

    settings = get_settings()

    container.register(MilvusStore, MilvusStore, singleton=True)
    container.register(EmbeddingService, EmbeddingService, singleton=True)
    container.register(LLMService, lambda: LLMService(settings), singleton=True)
    container.register(DocumentParser, DocumentParser, singleton=True)
    container.register(ChunkingEngine, ChunkingEngine, singleton=True)
    container.register(HybridRetriever, HybridRetriever, singleton=True)
    container.register(RerankerService, RerankerService, singleton=True)
    container.register(DocumentService, DocumentService, singleton=True)
    container.register(RAGService, RAGService, singleton=True)


# 应用启动时调用
_registered = False


def ensure_registered():
    global _registered
    if not _registered:
        _lazy_register_all()
        _registered = True


# ========================== 便利的 Depends 函数 ==========================
# 这些函数可直接用于 FastAPI Depends，同时兼容现有代码

def get_milvus_store():
    ensure_registered()
    from app.core.milvus_store import MilvusStore
    return container.resolve(MilvusStore)


def get_embedding_service():
    ensure_registered()
    from app.core.embedding import EmbeddingService
    return container.resolve(EmbeddingService)


def get_llm_service():
    ensure_registered()
    from app.core.llm import LLMService
    return container.resolve(LLMService)


def get_parser():
    ensure_registered()
    from app.core.parser import DocumentParser
    return container.resolve(DocumentParser)


def get_hybrid_retriever():
    ensure_registered()
    from app.core.retrieval import HybridRetriever
    return container.resolve(HybridRetriever)


def get_chunking_engine():
    ensure_registered()
    from app.core.chunking import ChunkingEngine
    return container.resolve(ChunkingEngine)


def get_reranker_service():
    ensure_registered()
    from app.core.reranker import RerankerService
    return container.resolve(RerankerService)


def get_document_service():
    ensure_registered()
    from app.services.document_service import DocumentService
    return container.resolve(DocumentService)


def get_rag_service():
    ensure_registered()
    from app.services.rag_service import RAGService
    return container.resolve(RAGService)
