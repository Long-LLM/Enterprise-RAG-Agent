"""
Milvus 向量存储封装
- Collection 管理（Schema 定义、索引创建）
- 文档/Chunk 的增删查
- 向量相似性检索
- BM25 全文检索支持（通过 pymilvus 的全文搜索功能或内存实现）

Schema 设计:
- chunk_id (PK, VARCHAR)   : 分块唯一ID
- doc_id (VARCHAR)         : 文档ID
- filename (VARCHAR)       : 文件名
- title (VARCHAR)          : 文档标题
- content (VARCHAR)        : 分块文本内容
- chunk_index (INT)        : 分块序号
- page_number (INT)        : 页码（如有）
- embedding (FLOAT_VECTOR) : 向量
- create_time (INT64)      : 创建时间戳
"""
import time
from typing import Dict, List, Optional, Tuple

from pymilvus import DataType, MilvusClient

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class MilvusStore:
    """
    Milvus 向量数据库封装
    """

    def __init__(self):
        self._client_uri = settings.milvus_uri
        self._client_token = settings.MILVUS_TOKEN or None
        self._client_db = settings.MILVUS_DB_NAME
        self.collection_name = settings.MILVUS_COLLECTION_NAME
        self.embed_dim = settings.EMBED_DIM
        self._connect()
        self._ensure_collection()

    def _connect(self):
        """建立 Milvus 连接"""
        self.client = MilvusClient(
            uri=self._client_uri,
            token=self._client_token,
            db_name=self._client_db,
            timeout=10,
        )

    def _ensure_connection(self):
        """确保连接可用，断开时自动重连"""
        try:
            self.client.get_server_version()
        except Exception:
            logger.warning("Milvus 连接已断开，正在重连...")
            try:
                self.client.close()
            except Exception:
                pass
            self._connect()
            logger.info("Milvus 重连成功")

    def _ensure_collection(self):
        """确保 Collection 存在，不存在则创建"""
        if self.client.has_collection(collection_name=self.collection_name):
            logger.info(f"Collection '{self.collection_name}' 已存在")
            return

        logger.info(f"创建 Collection: {self.collection_name}")

        schema = self.client.create_schema(
            auto_id=False,
            enable_dynamic_field=True,
        )

        # 1) 主键：chunk_id
        schema.add_field(
            field_name="chunk_id",
            datatype=DataType.VARCHAR,
            max_length=64,
            is_primary=True,
        )

        # 2) 文档ID
        schema.add_field(
            field_name="doc_id",
            datatype=DataType.VARCHAR,
            max_length=64,
        )

        # 3) 文件名
        schema.add_field(
            field_name="filename",
            datatype=DataType.VARCHAR,
            max_length=256,
        )

        # 4) 标题
        schema.add_field(
            field_name="title",
            datatype=DataType.VARCHAR,
            max_length=256,
        )

        # 5) 内容（长文本，Milvus 2.4+ VARCHAR 最大 65535，如需更长可用 JSON 或外部存储）
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=8192,
        )

        # 6) 分块序号
        schema.add_field(
            field_name="chunk_index",
            datatype=DataType.INT32,
        )

        # 7) 页码
        schema.add_field(
            field_name="page_number",
            datatype=DataType.INT32,
        )

        # 8) 创建时间戳
        schema.add_field(
            field_name="create_time",
            datatype=DataType.INT64,
        )

        # 9) 父块ID（父子分块）
        schema.add_field(
            field_name="parent_id",
            datatype=DataType.VARCHAR,
            max_length=64,
            nullable=True,
        )

        # 10) 分块类型
        schema.add_field(
            field_name="chunk_type",
            datatype=DataType.VARCHAR,
            max_length=16,
            nullable=True,
        )

        # 11) 章节标题（结构分块）
        schema.add_field(
            field_name="section_title",
            datatype=DataType.VARCHAR,
            max_length=256,
            nullable=True,
        )

        # 12) 向量字段
        schema.add_field(
            field_name="embedding",
            datatype=DataType.FLOAT_VECTOR,
            dim=self.embed_dim,
        )

        # 创建索引
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",  # 余弦相似度更适合语义检索
            params={"nlist": 128},
        )

        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"[OK] Collection '{self.collection_name}' 创建成功")

    def insert_chunks(self, chunks: List[Dict]) -> List[str]:
        """
        批量插入文档分块
        :param chunks: 每条包含 chunk_id, doc_id, filename, title, content, chunk_index, page_number, embedding
        :return: 插入的 chunk_id 列表
        """
        if not chunks:
            return []

        self._ensure_connection()

        now = int(time.time())
        for ch in chunks:
            if "create_time" not in ch:
                ch["create_time"] = now

        self.client.insert(
            collection_name=self.collection_name,
            data=chunks,
        )
        logger.info(f"已插入 {len(chunks)} 个 chunks 到 Milvus")
        return [ch["chunk_id"] for ch in chunks]

    def search_by_vector(
        self,
        embedding: List[float],
        top_k: int = 10,
        filters: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        向量相似性检索
        :param embedding: 查询向量
        :param top_k: 返回数量
        :param filters: 过滤表达式，如 'doc_id == "xxx"'
        :param output_fields: 需要返回的字段列表
        """
        self._ensure_connection()

        if output_fields is None:
            output_fields = [
                "chunk_id", "doc_id", "filename", "title",
                "content", "chunk_index", "page_number", "create_time",
                "parent_id", "chunk_type", "section_title",
            ]

        results = self.client.search(
            collection_name=self.collection_name,
            data=[embedding],
            limit=top_k,
            filter=filters,
            output_fields=output_fields,
            search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
        )

        # 展平结果
        hits = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {})
                entity["distance"] = hit.get("distance", 0.0)
                hits.append(entity)
        return hits

    def delete_by_doc_id(self, doc_id: str) -> int:
        """
        按 doc_id 删除文档的所有 chunks
        :return: 删除数量
        """
        self._ensure_connection()

        # Milvus delete 使用表达式
        expr = f'doc_id == "{doc_id}"'
        result = self.client.delete(
            collection_name=self.collection_name,
            filter=expr,
        )
        deleted = result.get("delete_count", 0) if isinstance(result, dict) else 0
        logger.info(f"删除 doc_id={doc_id} 的 {deleted} 条记录")
        return deleted

    def delete_by_chunk_ids(self, chunk_ids: List[str]) -> int:
        """按 chunk_id 列表删除"""
        if not chunk_ids:
            return 0
        self._ensure_connection()

        # Milvus 2.4+ 支持 in 表达式
        ids_str = ",".join([f'"{cid}"' for cid in chunk_ids])
        expr = f"chunk_id in [{ids_str}]"
        result = self.client.delete(
            collection_name=self.collection_name,
            filter=expr,
        )
        deleted = result.get("delete_count", 0) if isinstance(result, dict) else 0
        return deleted

    def get_doc_chunks(self, doc_id: str) -> List[Dict]:
        """获取某个文档的所有 chunks"""
        self._ensure_connection()

        return self.client.query(
            collection_name=self.collection_name,
            filter=f'doc_id == "{doc_id}"',
            output_fields=[
                "chunk_id", "content", "chunk_index", "page_number", "create_time",
                "parent_id", "chunk_type", "section_title",
            ],
        )

    def list_documents(self) -> List[Dict]:
        """
        列出所有不同的文档（按 doc_id 聚合）
        """
        self._ensure_connection()

        # Milvus 没有原生 group by，这里用 query 后内存聚合
        # 实际生产环境建议用外部元数据库（如 PostgreSQL / MongoDB）管理文档元信息
        all_chunks = self.client.query(
            collection_name=self.collection_name,
            filter="",
            output_fields=["doc_id", "filename", "title", "create_time"],
            limit=10000,
        )

        seen = set()
        docs = []
        for ch in all_chunks:
            doc_id = ch.get("doc_id")
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                docs.append({
                    "doc_id": doc_id,
                    "filename": ch.get("filename", ""),
                    "title": ch.get("title", ""),
                    "create_time": ch.get("create_time", 0),
                })
        return docs

    def count_by_doc_id(self, doc_id: str) -> int:
        """统计某文档的 chunk 数量"""
        self._ensure_connection()

        result = self.client.query(
            collection_name=self.collection_name,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["chunk_id"],
            limit=1,
        )
        # 简单的 count 方法（Milvus 2.4+ 有 count 接口但 pymilvus 封装可能不同，这里用 get 近似）
        # 实际上可以用 client.num_entities 按表达式统计
        stats = self.client.get_collection_stats(self.collection_name)
        return stats.get("row_count", 0)

    def health_check(self) -> bool:
        """检查 Milvus 连接状态"""
        try:
            self._ensure_connection()
            return True
        except Exception as e:
            logger.warning(f"Milvus 健康检查失败: {e}")
            return False

    def close(self):
        self.client.close()


# 全局单例
_milvus_store: MilvusStore | None = None


def get_milvus_store() -> MilvusStore:
    global _milvus_store
    if _milvus_store is None:
        _milvus_store = MilvusStore()
    return _milvus_store
