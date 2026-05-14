"""
分块预览 API
POST /api/chunk-preview - 上传文件预览分块效果（不入库）
"""
import json
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from app.config import get_settings
from app.core.chunking import get_chunking_engine
from app.core.parser import get_parser
from app.logger import get_logger
from app.models.schemas import BaseResponse, ChunkPreviewResponse

logger = get_logger(__name__)
router = APIRouter(tags=["Chunk Preview"])


@router.post("/chunk-preview", response_model=ChunkPreviewResponse)
async def preview_chunks(
    file: UploadFile = File(..., description="上传的文档文件"),
    strategy: str = Form(default="auto", description="分块策略"),
    chunk_size: Optional[int] = Form(default=None, description="块大小"),
    chunk_overlap: Optional[int] = Form(default=None, description="重叠大小"),
    parent_chunk_size: Optional[int] = Form(default=None, description="父块大小（父子分块）"),
    child_chunk_size: Optional[int] = Form(default=None, description="子块大小（父子分块）"),
    heading_levels: Optional[str] = Form(default=None, description="保留标题层级，JSON 数组如 [1,2,3]"),
    preserve_tables: Optional[bool] = Form(default=True, description="表格是否单独成块"),
    strategy_params: Optional[str] = Form(default=None, description="策略参数 JSON 对象"),
):
    """
    预览分块效果（不入库，不生成 embedding）
    """
    if not file.filename:
        return BaseResponse(code=400, message="文件名不能为空")

    # 读取文件内容
    content = await file.read()
    if not content:
        return BaseResponse(code=400, message="文件内容为空")

    # 限制预览文件大小
    max_preview_size = getattr(get_settings(), "CHUNK_PREVIEW_MAX_CHARS", 30000)
    if len(content) > max_preview_size * 3:  # 二进制文件可能更大
        logger.info(f"预览文件过大 ({len(content)} bytes)，仅预览前 {max_preview_size} 字符")

    try:
        # 1. 解析文档
        parser = get_parser()
        file_path = parser.save_upload(content, file.filename)
        parsed = await parser.parse(file_path, file.filename)

        if parsed.is_empty:
            return BaseResponse(code=400, message="文档解析结果为空")

        preview_text = parsed.text[:max_preview_size] if len(parsed.text) > max_preview_size else parsed.text

        # 2. 构建策略参数
        kwargs = {}
        if chunk_size is not None:
            kwargs["chunk_size"] = chunk_size
        if chunk_overlap is not None:
            kwargs["chunk_overlap"] = chunk_overlap
        if parent_chunk_size is not None:
            kwargs["parent_chunk_size"] = parent_chunk_size
        if child_chunk_size is not None:
            kwargs["child_chunk_size"] = child_chunk_size
        if heading_levels is not None:
            try:
                kwargs["heading_levels"] = json.loads(heading_levels)
            except json.JSONDecodeError:
                kwargs["heading_levels"] = [1, 2, 3]
        if preserve_tables is not None:
            kwargs["preserve_tables"] = preserve_tables

        # 解析额外的策略参数
        if strategy_params:
            try:
                extra_params = json.loads(strategy_params)
                kwargs.update(extra_params)
            except json.JSONDecodeError:
                logger.warning(f"策略参数 JSON 解析失败: {strategy_params}")

        # 结构化分块需要结构化元素
        if strategy == "structured":
            from app.core.chunking import StructuredChunker
            chunker = StructuredChunker()
            structured_elements = chunker._extract_structure(parsed.text)
            kwargs["structured_elements"] = structured_elements

        # 3. 分块
        engine = get_chunking_engine()
        chunks = engine.chunk(preview_text, strategy=strategy, **kwargs)

        # 4. 构建预览结果
        chunk_previews = []
        for ch in chunks:
            chunk_previews.append({
                "index": ch.index,
                "content": ch.content,
                "char_count": len(ch.content),
                "section_title": ch.metadata.get("section_title"),
                "heading_level": ch.metadata.get("heading_level"),
                "chunk_type": ch.metadata.get("chunk_type", "normal"),
                "parent_id": ch.metadata.get("parent_id"),
                "metadata": ch.metadata,
            })

        # 统计信息
        char_counts = [len(c.content) for c in chunks]
        stats = {
            "avg_length": round(sum(char_counts) / max(len(char_counts), 1), 1),
            "max_length": max(char_counts) if char_counts else 0,
            "min_length": min(char_counts) if char_counts else 0,
            "total_chunks": len(chunks),
            "total_chars": len(parsed.text),
            "preview_truncated": len(parsed.text) > max_preview_size,
        }

        return ChunkPreviewResponse(
            data=ChunkPreviewResponse.PreviewData(
                strategy=strategy,
                total_chars=len(parsed.text),
                chunk_count=len(chunks),
                chunks=chunk_previews,
                stats=stats,
            )
        )

    except Exception as e:
        logger.error(f"分块预览失败: {e}", exc_info=True)
        return BaseResponse(code=500, message=f"分块预览失败: {str(e)}")
