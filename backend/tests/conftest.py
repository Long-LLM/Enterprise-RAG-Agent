"""
测试全局 fixtures

使用方式:
    pytest backend/tests/
    pytest backend/tests/test_auth.py -v
    pytest backend/tests/ -m "not integration" -v
"""
import os
import sys
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# 确保 backend 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 测试环境强制使用安全的 SECRET_KEY
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-tests-only-1234567890"
os.environ["METADATA_DB_URL"] = "sqlite+aiosqlite:///./test_metadata.db"
os.environ["MILVUS_HOST"] = "localhost"
os.environ["OLLAMA_HOST"] = "http://localhost:11434"
os.environ["LOG_LEVEL"] = "ERROR"


# ---------- 容器级 Mock（使用 DI 容器覆盖，而非 monkeypatch 模块变量） ----------
def _mock_milvus_store():
    """Mock MilvusStore：所有操作返回空结果，不触发网络连接"""
    mock = MagicMock()
    mock.health_check.return_value = True
    mock.insert_chunks.return_value = []
    mock.search_by_vector.return_value = []
    mock.delete_by_doc_id.return_value = 0
    mock.get_doc_chunks.return_value = []
    mock.list_documents.return_value = []
    mock.count_by_doc_id.return_value = 0
    mock.close.return_value = None
    return mock


def _mock_embedding_service():
    """Mock EmbeddingService"""
    mock = MagicMock()
    mock.embed_query = AsyncMock(return_value=[0.0] * 1024)
    mock.embed_documents = AsyncMock(return_value=[])
    mock.health_check = AsyncMock(return_value=True)
    mock.close = AsyncMock(return_value=None)
    return mock


def _mock_llm_service():
    """Mock LLMService"""
    mock = MagicMock()
    mock.chat = AsyncMock(return_value="这是测试回答")
    mock.chat_stream = AsyncMock(return_value=[])()
    mock.health_check = AsyncMock(return_value=True)
    mock.close = AsyncMock(return_value=None)
    return mock


@pytest.fixture(autouse=True, scope="session")
def mock_external_services():
    """
    全局 session 级别的 mock：通过 DI 容器覆盖外部服务
    避免测试时尝试连接 Milvus / Ollama
    """
    from app.container import container, ensure_registered
    from app.core.embedding import EmbeddingService
    from app.core.llm import LLMService
    from app.core.milvus_store import MilvusStore

    ensure_registered()
    container.override(MilvusStore, _mock_milvus_store())
    container.override(EmbeddingService, _mock_embedding_service())
    container.override(LLMService, _mock_llm_service())

    yield

    # 测试结束后清理容器
    container.reset_override()
    container.clear_singletons()


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    FastAPI 异步 HTTP 客户端 fixture
    注意：此 fixture 会复用应用 lifespan（启动/关闭事件）
    """
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_user() -> dict:
    """
    创建一个测试用户，返回用户信息 dict
    用法: async def test_something(client, test_user):
    """
    from app.core.metadata_store import get_metadata_store
    from app.core.security import get_password_hash

    store = await get_metadata_store()
    user_id = "test_user_001"
    username = "testuser"
    password_hash = get_password_hash("testpass123")

    # 清理旧数据（如果存在）
    try:
        await store.delete_user(user_id)
    except Exception:
        pass

    await store.create_user(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        role="user",
    )

    return {
        "user_id": user_id,
        "username": username,
        "password": "testpass123",
        "role": "user",
    }


@pytest.fixture
async def admin_user() -> dict:
    """创建一个管理员测试用户"""
    from app.core.metadata_store import get_metadata_store
    from app.core.security import get_password_hash

    store = await get_metadata_store()
    user_id = "admin_user_001"
    username = "adminuser"
    password_hash = get_password_hash("adminpass123")

    try:
        await store.delete_user(user_id)
    except Exception:
        pass

    await store.create_user(
        user_id=user_id,
        username=username,
        password_hash=password_hash,
        role="admin",
    )

    return {
        "user_id": user_id,
        "username": username,
        "password": "adminpass123",
        "role": "admin",
    }


@pytest.fixture
async def auth_headers(client: AsyncClient, test_user: dict) -> dict:
    """
    已登录用户的认证 headers
    返回: {"Authorization": "Bearer <token>"}
    """
    resp = await client.post("/api/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"],
    })
    data = resp.json()
    token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_headers(client: AsyncClient, admin_user: dict) -> dict:
    """管理员认证 headers"""
    resp = await client.post("/api/auth/login", json={
        "username": admin_user["username"],
        "password": admin_user["password"],
    })
    data = resp.json()
    token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
async def clean_test_db():
    """
    每个测试函数结束后清理测试数据库中的测试数据
    autouse=True 表示自动应用于所有测试
    """
    yield
    # 测试结束后清理
    from app.core.metadata_store import _metadata_store
    try:
        if _metadata_store is not None:
            for uid in ["test_user_001", "admin_user_001"]:
                try:
                    await _metadata_store.delete_user(uid)
                except Exception:
                    pass
            await _metadata_store.close()
    except Exception:
        pass
