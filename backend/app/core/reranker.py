"""
重排序模块 (Reranker)
当前：使用 bge-reranker 模型
- 对混合检索的候选结果进行精排
- 支持本地模型加载或调用远程服务
"""
from typing import Dict, List

import httpx

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class RerankerService:
    """
    重排序服务
    对候选文档列表按与查询的相关性重新排序
    """

    def __init__(self):
        self.model_name = settings.RERANKER_MODEL
        self._local_model = None
        self._initialized = False

    def _init_local_model(self):
        """懒加载本地重排序模型"""
        if self._initialized:
            return
        try:
            # 尝试加载本地 FlagEmbedding 的 reranker
            from FlagEmbedding import FlagAutoReranker

            logger.info(f"正在加载重排序模型: {self.model_name}")
            self._local_model = FlagAutoReranker.from_finetuned(
                self.model_name,
                use_fp16=True,
                devices="cuda:0",  # 如有 GPU 则使用
            )
            self._initialized = True
            logger.info("重排序模型加载完成")
        except Exception as e:
            logger.warning(f"本地重排序模型加载失败: {e}，将使用基础打分降级")
            self._initialized = True

    async def rerank(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int = 5,
    ) -> List[Dict]:
        """
        对候选结果重排序
        :param query: 查询文本
        :param candidates: 候选列表，每项包含 content 和 score
        :param top_k: 返回前 K 个
        :return: 重排后的候选列表
        """
        if not candidates:
            return []

        passages = [c.get("content", "") for c in candidates]

        # 尝试本地模型重排
        if self._local_model is not None:
            scores = self._local_model.compute_score(
                query=query,
                passages=passages,
                batch_size=8,
            )
        else:
            # 降级：使用 Ollama 或简单规则打分
            # 这里先实现一个简单的基于 Ollama 的打分方式（可选）
            # 或者直接用原始分数作为降级
            scores = await self._fallback_score(query, passages)

        # 绑定分数并排序
        for i, candidate in enumerate(candidates):
            candidate["rerank_score"] = float(scores[i]) if i < len(scores) else 0.0

        sorted_candidates = sorted(
            candidates,
            key=lambda x: x.get("rerank_score", x.get("distance", 0)),
            reverse=True,
        )
        return sorted_candidates[:top_k]

    async def _fallback_score(self, query: str, passages: List[str]) -> List[float]:
        """
        降级打分方案：
        - 如果本地模型不可用，尝试通过 Ollama 的 embedding 做余弦相似度
        - 或者直接返回原始分数（不做重排）
        """
        from app.core.embedding import get_embedding_service

        embed_service = get_embedding_service()
        try:
            # 批量获取 query 和 passages 的 embedding
            query_embed = await embed_service.embed_query(query)
            passage_embeds = await embed_service.embed_documents(passages)

            import numpy as np

            q_vec = np.array(query_embed)
            scores = []
            for p_vec in passage_embeds:
                # 余弦相似度
                p_arr = np.array(p_vec)
                cos_sim = np.dot(q_vec, p_arr) / (np.linalg.norm(q_vec) * np.linalg.norm(p_arr) + 1e-8)
                scores.append(float(cos_sim))
            return scores
        except Exception as e:
            logger.warning(f"降级打分失败: {e}，返回均等分数")
            return [0.5] * len(passages)


# 全局单例
_reranker_service: RerankerService | None = None


def get_reranker_service() -> RerankerService:
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService()
    return _reranker_service
