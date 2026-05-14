"""
文档处理编排服务
完整流程：上传 → 解析 → 清洗 → 智能分块 → Embedding → 存入 Milvus → 更新 BM25 索引
"""
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from app.config import get_settings
from app.core.chunking import get_chunking_engine, TextChunk
from app.core.embedding import get_embedding_service
from app.core.metadata_store import get_metadata_store
from app.core.milvus_store import get_milvus_store
from app.core.parser import get_parser, ParsedDocument
from app.core.retrieval import get_hybrid_retriever
from app.logger import get_logger, log_performance
from app.models.schemas import DocumentInfo

logger = get_logger(__name__)
settings = get_settings()


class DocumentService:
    """
    文档处理服务
    负责文档全生命周期管理
    """

    def __init__(self):
        self.parser = get_parser()
        self.chunk_engine = get_chunking_engine()
        self.embed_service = get_embedding_service()
        self.milvus = get_milvus_store()
        self.retriever = get_hybrid_retriever()

    @log_performance(level=20, log_args=False)
    async def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        title: Optional[str] = None,
        chunk_strategy: str = "auto",
        strategy_params: Optional[Dict] = None,
        department: Optional[str] = None,
    ) -> Dict:
        """
        处理上传的文档
        :param file_bytes: 文件二进制内容
        :param filename: 原始文件名
        :param title: 文档标题（可选）
        :param chunk_strategy: 分块策略
        :param strategy_params: 策略特定参数
        :param department: 文档所属部门/数据库
        :return: 处理结果 {doc_id, filename, chunk_count, status}
        """
        doc_id = str(uuid.uuid4())
        logger.info(f"[{doc_id}] 开始处理文档: {filename}, 策略: {chunk_strategy}")

        try:
            # 1. 保存文件
            file_path = self.parser.save_upload(file_bytes, filename)

            # 2. 解析文档
            parsed: ParsedDocument = await self.parser.parse(file_path, filename)
            if parsed.is_empty:
                raise ValueError(f"文档解析结果为空: {filename}")

            doc_title = title or parsed.metadata.get("title") or filename
            logger.info(f"[{doc_id}] 文档解析完成，文本长度: {len(parsed.text)}")

            # 3. 准备分块参数
            kwargs = strategy_params or {}

            # 结构化分块需要结构化元素
            if chunk_strategy == "structured":
                from app.core.chunking import StructuredChunker
                chunker = StructuredChunker()
                structured_elements = chunker._extract_structure(parsed.text)
                kwargs["structured_elements"] = structured_elements

            # 4. 智能分块
            chunks: List[TextChunk] = self.chunk_engine.chunk(
                text=parsed.text,
                strategy=chunk_strategy,
                **kwargs,
            )
            logger.info(f"[{doc_id}] 分块完成，共 {len(chunks)} 个 chunks")

            if not chunks:
                raise ValueError("分块结果为空")

            # 5. Embedding
            chunk_texts = [ch.content for ch in chunks]
            embeddings = await self.embed_service.embed_documents(chunk_texts)
            logger.info(f"[{doc_id}] Embedding 完成，维度: {len(embeddings[0]) if embeddings else 0}")

            # 6. 组装 Milvus 数据
            now = int(time.time())
            milvus_chunks = []
            metadata_chunks = []
            for i, ch in enumerate(chunks):
                chunk_id = f"{doc_id}_{i}"
                parent_id = ch.metadata.get("parent_id")
                chunk_type = ch.metadata.get("chunk_type", "normal")
                section_title = ch.metadata.get("section_title")
                heading_level = ch.metadata.get("heading_level")

                milvus_chunks.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "filename": filename,
                    "title": doc_title,
                    "content": ch.content[:8190],
                    "chunk_index": ch.index,
                    "page_number": ch.metadata.get("page_number", 0),
                    "embedding": embeddings[i],
                    "create_time": now,
                    # 新增字段（通过动态字段或显式字段）
                    "parent_id": parent_id,
                    "chunk_type": chunk_type,
                    "section_title": section_title,
                    "heading_level": heading_level,
                })

                metadata_chunks.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "parent_id": parent_id,
                    "chunk_type": chunk_type,
                    "content": ch.content,
                    "chunk_index": ch.index,
                    "section_title": section_title,
                    "heading_level": heading_level,
                    "page_number": ch.metadata.get("page_number", 0),
                    "char_count": len(ch.content),
                    "metadata": ch.metadata,
                    "created_at": now,
                })

            # 7. 插入 Milvus
            self.milvus.insert_chunks(milvus_chunks)
            logger.info(f"[{doc_id}] 已插入 {len(milvus_chunks)} chunks 到 Milvus")

            # 8. 保存元数据到 SQLite
            try:
                meta_store = await get_metadata_store()
                await meta_store.save_document({
                    "doc_id": doc_id,
                    "filename": filename,
                    "title": doc_title,
                    "file_type": Path(filename).suffix.lower().lstrip("."),
                    "chunk_strategy": chunk_strategy,
                    "chunk_count": len(chunks),
                    "file_size_bytes": len(file_bytes),
                    "department": department,
                    "created_at": now,
                })
                await meta_store.save_chunks(metadata_chunks)
                logger.info(f"[{doc_id}] 元数据已保存到 SQLite")
            except Exception as e:
                logger.warning(f"[{doc_id}] 元数据保存失败（非关键）: {e}")

            # 9. 更新 BM25 索引（增量）
            for ch in milvus_chunks:
                self.retriever.add_to_bm25(ch)
            logger.info(f"[{doc_id}] BM25 索引已更新")

            return {
                "doc_id": doc_id,
                "filename": filename,
                "title": doc_title,
                "chunk_count": len(chunks),
                "status": "success",
            }

        except Exception as e:
            logger.error(f"[{doc_id}] 文档处理失败: {e}", exc_info=True)
            # 清理已插入数据（尽力而为）
            try:
                self.milvus.delete_by_doc_id(doc_id)
            except Exception:
                pass
            try:
                meta_store = await get_metadata_store()
                await meta_store.delete_document(doc_id)
            except Exception:
                pass
            raise

    async def list_documents(self) -> List[DocumentInfo]:
        """列出所有已入库的文档（从元数据库获取完整信息）"""
        store = await get_metadata_store()
        docs = await store.list_documents()
        result = []
        for d in docs:
            result.append(
                DocumentInfo(
                    doc_id=d["doc_id"],
                    filename=d["filename"],
                    title=d.get("title"),
                    chunk_count=d.get("chunk_count", 0),
                    file_type=d.get("file_type") or (Path(d["filename"]).suffix.lower().lstrip(".") if d.get("filename") else None),
                    file_size=d.get("file_size_bytes"),
                    department=d.get("department"),
                    created_at=None,
                    status="active",
                )
            )
        return result

    async def delete_document(self, doc_id: str) -> int:
        """
        删除文档及其所有 chunks
        """
        # 1. 从 Milvus 删除
        deleted = self.milvus.delete_by_doc_id(doc_id)
        # 2. 从 SQLite 删除
        try:
            meta_store = await get_metadata_store()
            await meta_store.delete_document(doc_id)
        except Exception as e:
            logger.warning(f"删除元数据失败: {e}")
        # 3. 重建 BM25 索引
        all_docs = []
        for chunk in self._get_all_chunks_for_bm25():
            all_docs.append({
                "chunk_id": chunk.get("chunk_id"),
                "content": chunk.get("content", ""),
            })
        self.retriever.build_bm25_index(all_docs)
        logger.info(f"已删除文档 {doc_id}，重建 BM25 索引")
        return deleted

    async def get_document_chunks(self, doc_id: str) -> List[Dict]:
        """获取文档的所有 chunks"""
        return self.milvus.get_doc_chunks(doc_id)

    async def rebuild_bm25_index(self):
        """全量重建 BM25 索引（管理后台用）"""
        all_docs = []
        for chunk in self._get_all_chunks_for_bm25():
            all_docs.append({
                "chunk_id": chunk.get("chunk_id"),
                "content": chunk.get("content", ""),
            })
        self.retriever.build_bm25_index(all_docs)
        logger.info(f"BM25 索引全量重建完成: {len(all_docs)} 条记录")

    def _get_all_chunks_for_bm25(self):
        """获取所有 chunks 用于重建 BM25（分页查询，避免超过 Milvus 最大窗口限制）"""
        self.milvus._ensure_connection()
        batch_size = 16384
        all_chunks = []
        offset = 0
        while True:
            batch = self.milvus.client.query(
                collection_name=self.milvus.collection_name,
                filter="",
                output_fields=["chunk_id", "content"],
                limit=batch_size,
                offset=offset,
            )
            if not batch:
                break
            all_chunks.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
        return all_chunks


# 全局单例
_document_service: DocumentService | None = None


def get_document_service() -> DocumentService:
    global _document_service
    if _document_service is None:
        _document_service = DocumentService()
    return _document_service
