"""
Celery 异步任务定义

核心任务：
- process_document: 文档处理全流程（解析 → 分块 → Embedding → 存储）
- rebuild_bm25_index: 全量重建 BM25 索引

状态流转：
    PENDING -> STARTED -> PROGRESS -> SUCCESS / FAILURE / RETRY
"""
import asyncio
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from celery import states
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from app.config import get_settings
from app.core.celery_app import celery_app
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ---------- 辅助：在 Celery 同步上下文中运行 async 代码 ----------

def _run_async(coro):
    """在同步上下文中运行异步协程"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果已经在事件循环中（如 FastAPI），使用 run_coroutine_threadsafe
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=3600)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # 没有事件循环，创建新的
        return asyncio.run(coro)


# ---------- 文档处理任务 ----------

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="doc_process",
)
def process_document(
    self,
    file_path: str,
    filename: str,
    title: Optional[str] = None,
    chunk_strategy: str = "auto",
    strategy_params: Optional[Dict] = None,
    department: Optional[str] = None,
) -> Dict:
    """
    异步文档处理任务

    :param file_path: 文件在服务器上的临时路径
    :param filename: 原始文件名
    :param title: 文档标题
    :param chunk_strategy: 分块策略
    :param strategy_params: 策略参数
    :param department: 所属部门
    :return: 处理结果 dict
    """
    doc_id = str(uuid.uuid4())
    logger.info(f"[Task {self.request.id}] 开始处理文档: {filename}, doc_id={doc_id}")

    # 更新任务状态为"处理中"
    self.update_state(
        state="PROGRESS",
        meta={
            "doc_id": doc_id,
            "filename": filename,
            "stage": "started",
            "progress": 0,
            "message": "开始处理...",
        },
    )

    try:
        from app.core.parser import get_parser, ParsedDocument
        from app.core.chunking import get_chunking_engine, TextChunk
        from app.core.embedding import get_embedding_service
        from app.core.milvus_store import get_milvus_store
        from app.core.metadata_store import get_metadata_store
        from app.core.retrieval import get_hybrid_retriever

        # ---- Stage 1: 解析文档 ----
        self.update_state(
            state="PROGRESS",
            meta={
                "doc_id": doc_id,
                "filename": filename,
                "stage": "parsing",
                "progress": 10,
                "message": "正在解析文档...",
            },
        )

        parser = get_parser()
        parsed: ParsedDocument = _run_async(parser.parse(file_path, filename))
        if parsed.is_empty:
            raise ValueError(f"文档解析结果为空: {filename}")

        doc_title = title or parsed.metadata.get("title") or filename
        logger.info(f"[Task {self.request.id}] 解析完成，文本长度: {len(parsed.text)}")

        # ---- Stage 2: 分块 ----
        self.update_state(
            state="PROGRESS",
            meta={
                "doc_id": doc_id,
                "filename": filename,
                "stage": "chunking",
                "progress": 30,
                "message": "正在分块...",
            },
        )

        chunk_engine = get_chunking_engine()
        kwargs = strategy_params or {}

        if chunk_strategy == "structured":
            from app.core.chunking import StructuredChunker
            chunker = StructuredChunker()
            structured_elements = chunker._extract_structure(parsed.text)
            kwargs["structured_elements"] = structured_elements

        chunks: List[TextChunk] = chunk_engine.chunk(
            text=parsed.text,
            strategy=chunk_strategy,
            **kwargs,
        )
        logger.info(f"[Task {self.request.id}] 分块完成: {len(chunks)} chunks")

        if not chunks:
            raise ValueError("分块结果为空")

        # ---- Stage 3: Embedding ----
        self.update_state(
            state="PROGRESS",
            meta={
                "doc_id": doc_id,
                "filename": filename,
                "stage": "embedding",
                "progress": 50,
                "message": f"正在生成 Embedding ({len(chunks)} chunks)...",
            },
        )

        embed_service = get_embedding_service()
        chunk_texts = [ch.content for ch in chunks]
        embeddings = _run_async(embed_service.embed_documents(chunk_texts))
        logger.info(f"[Task {self.request.id}] Embedding 完成")

        # ---- Stage 4: 存入 Milvus ----
        self.update_state(
            state="PROGRESS",
            meta={
                "doc_id": doc_id,
                "filename": filename,
                "stage": "storing",
                "progress": 75,
                "message": "正在存入向量数据库...",
            },
        )

        now = int(time.time())
        milvus = get_milvus_store()
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

        milvus.insert_chunks(milvus_chunks)

        # ---- Stage 5: 保存元数据 ----
        meta_store = _run_async(get_metadata_store())
        _run_async(meta_store.save_document({
            "doc_id": doc_id,
            "filename": filename,
            "title": doc_title,
            "file_type": Path(filename).suffix.lower().lstrip("."),
            "chunk_strategy": chunk_strategy,
            "chunk_count": len(chunks),
            "file_size_bytes": Path(file_path).stat().st_size if Path(file_path).exists() else 0,
            "department": department,
            "created_at": now,
        }))
        _run_async(meta_store.save_chunks(metadata_chunks))

        # ---- Stage 6: 更新 BM25 ----
        retriever = get_hybrid_retriever()
        for ch in milvus_chunks:
            retriever.add_to_bm25(ch)

        # ---- Stage 7: 清理临时文件 ----
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass

        logger.info(f"[Task {self.request.id}] 文档处理完成: {doc_id}")

        return {
            "doc_id": doc_id,
            "filename": filename,
            "title": doc_title,
            "chunk_count": len(chunks),
            "status": "success",
            "task_id": self.request.id,
        }

    except SoftTimeLimitExceeded:
        logger.error(f"[Task {self.request.id}] 处理超时")
        # 尝试清理
        _cleanup_failed_doc(doc_id)
        raise

    except Exception as exc:
        logger.error(f"[Task {self.request.id}] 文档处理失败: {exc}", exc_info=True)
        _cleanup_failed_doc(doc_id)

        # 重试逻辑
        if self.request.retries < self.max_retries:
            logger.info(f"[Task {self.request.id}] 将在 60 秒后重试 (第 {self.request.retries + 1}/{self.max_retries} 次)")
            raise self.retry(exc=exc, countdown=60)

        # 超过最大重试次数
        raise MaxRetriesExceededError(
            f"文档处理失败，已重试 {self.max_retries} 次: {exc}"
        )


# ---------- 维护任务 ----------

@celery_app.task(bind=True, queue="maintenance")
def rebuild_bm25_index(self) -> Dict:
    """全量重建 BM25 索引"""
    from app.core.retrieval import get_hybrid_retriever
    from app.core.milvus_store import get_milvus_store

    self.update_state(state="PROGRESS", meta={"stage": "rebuilding", "message": "正在重建 BM25 索引..."})

    milvus = get_milvus_store()
    retriever = get_hybrid_retriever()

    batch_size = 16384
    offset = 0
    all_docs = []

    while True:
        batch = milvus.client.query(
            collection_name=milvus.collection_name,
            filter="",
            output_fields=["chunk_id", "content"],
            limit=batch_size,
            offset=offset,
        )
        if not batch:
            break
        for item in batch:
            all_docs.append({
                "chunk_id": item.get("chunk_id"),
                "content": item.get("content", ""),
            })
        if len(batch) < batch_size:
            break
        offset += batch_size

    retriever.build_bm25_index(all_docs)

    logger.info(f"BM25 索引重建完成: {len(all_docs)} 条记录")
    return {
        "status": "success",
        "total_chunks": len(all_docs),
    }


# ---------- 辅助函数 ----------

def _cleanup_failed_doc(doc_id: str):
    """清理失败文档的残留数据"""
    try:
        from app.core.milvus_store import get_milvus_store
        from app.core.metadata_store import get_metadata_store
        milvus = get_milvus_store()
        milvus.delete_by_doc_id(doc_id)
        meta_store = _run_async(get_metadata_store())
        _run_async(meta_store.delete_document(doc_id))
    except Exception as e:
        logger.warning(f"清理失败文档残留时出错: {e}")
