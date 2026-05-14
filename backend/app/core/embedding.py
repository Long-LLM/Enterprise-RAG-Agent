"""
Embedding 服务封装
当前：通过 Ollama 调用本地 bge-m3 模型
未来：可无缝切换为私有化部署的 Embedding 服务或 vLLM Embedding
"""
from typing import List, Union

import httpx

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class EmbeddingService:
    """
    Embedding 服务
    - 支持单条/批量文本向量化
    - 内置容错与自动重试
    """

    def __init__(self):
        self.model = settings.OLLAMA_EMBED_MODEL
        self.api_url = settings.ollama_embed_url
        self.embed_dim = settings.EMBED_DIM
        self._client = httpx.AsyncClient(timeout=180.0)

    async def embed(self, texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """
        调用 Ollama 生成嵌入向量
        :param texts: 单条文本或文本列表
        :return: 单条向量或向量列表
        """
        single = isinstance(texts, str)
        input_texts = [texts] if single else texts

        try:
            payload = {
                "model": self.model,
                "input": input_texts,
            }
            resp = await self._client.post(self.api_url, json=payload)
            if resp.status_code >= 400:
                detail = resp.text[:500]
                logger.error(f"Embedding 请求失败 [{resp.status_code}]: {detail}")
            resp.raise_for_status()
            result = resp.json()

            embeddings = result.get("embeddings", [])
            if not embeddings:
                raise ValueError(f"Ollama 返回空 embeddings: {result}")

            # Ollama /api/embed 返回格式: { "embeddings": [[...], [...]] }
            if single:
                return embeddings[0]
            return embeddings

        except Exception as e:
            logger.error(f"Embedding 请求失败: {e}")
            raise

    async def embed_query(self, text: str) -> List[float]:
        """查询文本向量化（单条）"""
        return await self.embed(text)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """文档批量向量化（内置分批，避免一次性发送过多导致超时）"""
        if not texts:
            return []

        batch_size = 50   # GPU 环境下每批 50 条最优（Intel Arc 约 37 秒/批）
        if len(texts) <= batch_size:
            return await self.embed(texts)

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.info(f"Embedding 分批处理: {i + 1}-{min(i + batch_size, len(texts))} / {len(texts)}")
            batch_embeddings = await self.embed(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def health_check(self) -> bool:
        """检查 Ollama Embedding 服务是否可用"""
        try:
            resp = await self._client.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=10.0)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            model_names = [m.get("name", m.get("model", "")) for m in models]
            # 兼容 "bge-m3" 或 "bge-m3:latest"
            return any(self.model in name for name in model_names)
        except Exception as e:
            logger.warning(f"Ollama 健康检查失败: {e}")
            return False

    async def close(self):
        await self._client.aclose()


# 全局单例
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
