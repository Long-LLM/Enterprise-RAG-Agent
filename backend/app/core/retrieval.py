"""
混合检索模块 (Hybrid Retrieval)
- 向量检索：Milvus 语义相似度搜索
- 关键词检索：BM25 全文搜索（内存实现 + Milvus 全文索引预留）
- 融合排序：RRF (Reciprocal Rank Fusion) 或加权融合
"""
from typing import Dict, List, Optional

import numpy as np

from app.config import get_settings
from app.core.embedding import get_embedding_service
from app.core.milvus_store import get_milvus_store
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class BM25Index:
    """
    内存中的 BM25 索引
    用于关键词检索，与 Milvus 向量检索互补
    生产环境可替换为 Elasticsearch / Meilisearch
    """

    def __init__(self):
        self.documents: List[Dict] = []  # {chunk_id, content, metadata}
        self.tokenized_docs: List[List[str]] = []
        self.k1 = 1.5
        self.b = 0.75
        self.avgdl = 0.0
        self.df: Dict[str, int] = {}  # document frequency
        self.N = 0
        self._built = False

    def build(self, documents: List[Dict]):
        """构建 BM25 索引"""
        import jieba

        self.documents = documents
        self.tokenized_docs = []
        self.df = {}
        total_len = 0

        for doc in documents:
            content = doc.get("content", "")
            tokens = list(jieba.cut_for_search(content))
            self.tokenized_docs.append(tokens)
            total_len += len(tokens)

            # 更新 df
            seen = set(tokens)
            for t in seen:
                self.df[t] = self.df.get(t, 0) + 1

        self.N = len(documents)
        self.avgdl = total_len / max(self.N, 1)
        self._built = True
        logger.info(f"BM25 索引构建完成: {self.N} 篇文档")

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """BM25 搜索"""
        import jieba

        if not self._built or self.N == 0:
            return []

        tokens = list(jieba.cut_for_search(query))
        if not tokens:
            return []

        scores = []
        for idx, doc_tokens in enumerate(self.tokenized_docs):
            score = self._bm25_score(tokens, doc_tokens)
            scores.append((idx, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scores[:top_k]:
            doc = self.documents[idx].copy()
            doc["bm25_score"] = score
            results.append(doc)
        return results

    def _bm25_score(self, query_tokens: List[str], doc_tokens: List[str]) -> float:
        """计算单篇文档的 BM25 分数"""
        score = 0.0
        doc_len = len(doc_tokens)
        token_counts = {}
        for t in doc_tokens:
            token_counts[t] = token_counts.get(t, 0) + 1

        for t in query_tokens:
            if t not in self.df:
                continue
            idf = np.log((self.N - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1)
            tf = token_counts.get(t, 0)
            denom = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * (tf * (self.k1 + 1)) / max(denom, 1e-8)
        return score

    def add_document(self, doc: Dict):
        """增量添加文档（会触发重建）"""
        self.documents.append(doc)
        self.build(self.documents)

    def clear(self):
        """清空索引"""
        self.documents = []
        self.tokenized_docs = []
        self.df = {}
        self.N = 0
        self.avgdl = 0.0
        self._built = False


class HybridRetriever:
    """
    混合检索器
    1. 同时执行向量检索和 BM25 检索
    2. 使用 RRF 融合两者结果
    3. 可进一步调用重排序器精排
    """

    def __init__(self):
        self.milvus = get_milvus_store()
        self.embed_service = get_embedding_service()
        self.bm25 = BM25Index()
        self._bm25_built = False

    async def retrieve(
        self,
        query: str,
        top_k_vector: int = 10,
        top_k_bm25: int = 10,
        filters: Optional[str] = None,
        use_parent_context: bool = True,
    ) -> List[Dict]:
        """
        混合检索主入口
        :param use_parent_context: 父子分块时是否获取父块上下文
        :return: 融合排序后的候选列表
        """
        # 1. 向量检索
        query_embed = await self.embed_service.embed_query(query)
        vector_results = self.milvus.search_by_vector(
            embedding=query_embed,
            top_k=top_k_vector,
            filters=filters,
        )
        # 转换 distance 为 score（COSINE 距离越大越相似）
        for r in vector_results:
            r["score"] = r.get("distance", 0.0)
            r["source"] = "vector"

        # 2. BM25 检索（扩大范围后过滤）
        if self._bm25_built:
            bm25_results = self.bm25.search(query, top_k=top_k_bm25 * 3)
            # 如果有过滤条件，后过滤 BM25 结果
            if filters:
                allowed_doc_ids = self._parse_doc_id_filter(filters)
                if allowed_doc_ids is not None:
                    bm25_results = [r for r in bm25_results if r.get("doc_id") in allowed_doc_ids]
            bm25_results = bm25_results[:top_k_bm25]
            for r in bm25_results:
                r["score"] = r.get("bm25_score", 0.0)
                r["source"] = "bm25"
        else:
            bm25_results = []
            logger.warning("BM25 索引未构建，仅使用向量检索")

        # 3. RRF 融合
        fused = self._rrf_fuse(vector_results, bm25_results, k=60)

        # 4. 父子分块：获取父块上下文
        if use_parent_context:
            fused = await self._enrich_parent_context(fused)

        return fused

    def _parse_doc_id_filter(self, filters: str):
        """从 Milvus filter 表达式中提取允许的 doc_id 集合"""
        import re
        if not filters:
            return None
        if 'doc_id in [' in filters:
            part = filters.split('doc_id in [')[1].split(']')[0]
            matches = re.findall(r'"([^"]+)"', part)
            return set(matches)
        m = re.search(r'doc_id == "([^"]+)"', filters)
        if m:
            return {m.group(1)}
        return None

    async def _enrich_parent_context(self, results: List[Dict]) -> List[Dict]:
        """为子块补充父块上下文"""
        try:
            from app.core.metadata_store import get_metadata_store
            store = await get_metadata_store()
            for r in results:
                parent_id = r.get("parent_id")
                if parent_id and r.get("chunk_type") == "child":
                    parent = await store.get_parent_chunk(parent_id)
                    if parent:
                        r["parent_content"] = parent.get("content", "")
        except Exception as e:
            logger.warning(f"获取父块上下文失败: {e}")
        return results

    def _rrf_fuse(self, vector_results: List[Dict], bm25_results: List[Dict], k: int = 60) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF)
        score = Σ 1 / (k + rank)
        """
        scores: Dict[str, float] = {}
        metas: Dict[str, Dict] = {}

        def add_results(results: List[Dict], source: str):
            for rank, item in enumerate(results, start=1):
                chunk_id = item.get("chunk_id")
                if not chunk_id:
                    continue
                metas[chunk_id] = item
                # RRF 分数
                rrf_score = 1.0 / (k + rank)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score

        add_results(vector_results, "vector")
        add_results(bm25_results, "bm25")

        # 排序
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        fused = []
        for chunk_id, score in sorted_items:
            item = metas[chunk_id].copy()
            item["rrf_score"] = score
            fused.append(item)
        return fused

    def build_bm25_index(self, documents: List[Dict]):
        """
        构建/重建 BM25 索引
        通常在文档入库后调用
        :param documents: 所有 chunk 的列表，每项至少包含 chunk_id 和 content
        """
        self.bm25.build(documents)
        self._bm25_built = True
        logger.info("BM25 索引已构建")

    def add_to_bm25(self, doc: Dict):
        """增量添加单条文档到 BM25 索引"""
        self.bm25.add_document(doc)
        self._bm25_built = True


# 全局单例
_hybrid_retriever: HybridRetriever | None = None


def get_hybrid_retriever() -> HybridRetriever:
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever()
    return _hybrid_retriever
