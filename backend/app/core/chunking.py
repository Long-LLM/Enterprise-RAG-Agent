"""
智能分块策略模块 - Dify 风格分块引擎
支持 7 种策略：
- auto: 自动选择
- fixed_size: 固定大小分块
- recursive: 递归分块
- semantic: 语义分块
- structured: 结构分块
- parent_child: 父子分块
- llm_smart: LLM 智能分块
"""
import json
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ========================== 基础数据结构 ==========================

@dataclass
class TextChunk:
    """分块后的文本块对象"""

    content: str
    index: int
    start_pos: int = 0
    end_pos: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ========================== 抽象基类 ==========================

class BaseChunker(ABC):
    """分块器抽象基类"""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        """对文本进行分块，返回 TextChunk 列表"""
        pass

    def _get_param(self, kwargs: dict, key: str, default):
        """获取参数，优先从 kwargs 取，否则用默认值"""
        return kwargs.get(key, default)


# ========================== 1. 固定大小分块 ==========================

class FixedSizeChunker(BaseChunker):
    """
    固定大小分块
    按固定字符数切分，支持重叠窗口和自定义分隔符
    """

    name = "fixed_size"
    description = "按固定字符数均匀切分，适合结构化数据"

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        chunk_size = self._get_param(kwargs, "chunk_size", settings.CHUNK_SIZE)
        chunk_overlap = self._get_param(kwargs, "chunk_overlap", settings.CHUNK_OVERLAP)
        separator = self._get_param(kwargs, "separator", "")

        chunks: List[TextChunk] = []
        index = 0
        pos = 0

        # 先按 separator 分割
        if separator:
            parts = text.split(separator)
        else:
            parts = [text]

        current_buffer = ""
        current_start = 0

        for i, part in enumerate(parts):
            part_with_sep = part + separator if separator and i < len(parts) - 1 else part

            # 如果单个 part 本身就超过 chunk_size，需要先 flush 当前 buffer，
            # 然后强制把这个超长 part 按 chunk_size 切分
            if len(part_with_sep) > chunk_size:
                # 保存当前 buffer
                if current_buffer.strip():
                    chunks.append(
                        TextChunk(
                            content=current_buffer.strip(),
                            index=index,
                            start_pos=current_start,
                            end_pos=current_start + len(current_buffer),
                            metadata={"strategy": self.name, "char_count": len(current_buffer)},
                        )
                    )
                    index += 1
                    current_buffer = ""

                # 强制切分这个超长 part
                sub_pos = 0
                while sub_pos < len(part_with_sep):
                    sub_end = min(sub_pos + chunk_size, len(part_with_sep))
                    sub_text = part_with_sep[sub_pos:sub_end].strip()
                    if sub_text:
                        chunks.append(
                            TextChunk(
                                content=sub_text,
                                index=index,
                                start_pos=pos + sub_pos,
                                end_pos=pos + sub_end,
                                metadata={"strategy": self.name, "char_count": len(sub_text)},
                            )
                        )
                        index += 1
                    if sub_end >= len(part_with_sep):
                        break
                    sub_pos = sub_end - chunk_overlap
                    if sub_pos >= sub_end:  # 安全检查，防止死循环
                        sub_pos = sub_end
                pos += len(part_with_sep)
                current_start = pos
                continue

            if len(current_buffer) + len(part_with_sep) <= chunk_size:
                if not current_buffer:
                    current_start = pos
                current_buffer += part_with_sep
            else:
                # 保存当前块
                if current_buffer.strip():
                    chunks.append(
                        TextChunk(
                            content=current_buffer.strip(),
                            index=index,
                            start_pos=current_start,
                            end_pos=current_start + len(current_buffer),
                            metadata={"strategy": self.name, "char_count": len(current_buffer)},
                        )
                    )
                    index += 1

                # 重叠处理
                if chunk_overlap > 0 and len(current_buffer) > chunk_overlap:
                    overlap_text = current_buffer[-chunk_overlap:]
                    current_buffer = overlap_text + part_with_sep
                    current_start = current_start + len(current_buffer) - len(overlap_text) - len(part_with_sep)
                else:
                    current_buffer = part_with_sep
                    current_start = pos + len(current_buffer) - len(part_with_sep)

            pos += len(part_with_sep)

        # 处理剩余
        if current_buffer.strip():
            chunks.append(
                TextChunk(
                    content=current_buffer.strip(),
                    index=index,
                    start_pos=current_start,
                    end_pos=current_start + len(current_buffer),
                    metadata={"strategy": self.name, "char_count": len(current_buffer)},
                )
            )

        return chunks


# ========================== 2. 递归分块 ==========================

class RecursiveChunker(BaseChunker):
    """
    递归分块
    按分隔符优先级递归切分：段落 > 行 > 句子 > 单词 > 字符
    """

    name = "recursive"
    description = "按段落→句子→单词优先级递归切分，通用性强"

    DEFAULT_SEPARATORS = [
        "\n\n",  # 段落
        "\n",  # 行
        "。", "？", "！", ".", "?", "!",  # 句子
        " ",  # 单词
        "",  # 字符
    ]

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        chunk_size = self._get_param(kwargs, "chunk_size", settings.CHUNK_SIZE)
        chunk_overlap = self._get_param(kwargs, "chunk_overlap", settings.CHUNK_OVERLAP)
        separators = self._get_param(kwargs, "separators", self.DEFAULT_SEPARATORS)

        chunks: List[TextChunk] = []
        index = 0
        pos = 0
        remaining = text

        while remaining:
            if len(remaining) <= chunk_size:
                if remaining.strip():
                    chunks.append(
                        TextChunk(
                            content=remaining.strip(),
                            index=index,
                            start_pos=pos,
                            end_pos=pos + len(remaining),
                            metadata={"strategy": self.name, "char_count": len(remaining)},
                        )
                    )
                break

            split_point = self._find_split_point(remaining, chunk_size, separators)
            chunk_text = remaining[:split_point].strip()

            if chunk_text:
                chunks.append(
                    TextChunk(
                        content=chunk_text,
                        index=index,
                        start_pos=pos,
                        end_pos=pos + split_point,
                        metadata={"strategy": self.name, "char_count": len(chunk_text)},
                    )
                )
                index += 1

            # 滑动窗口（重叠）
            step = max(split_point - chunk_overlap, chunk_size // 2)
            pos += step
            remaining = remaining[step:]

        return chunks

    def _find_split_point(self, text: str, target_size: int, separators: List[str]) -> int:
        """找到最接近 target_size 的语义分割点"""
        best_point = target_size

        for sep in separators:
            if not sep:
                continue
            search_area = text[: target_size + 100]
            last_idx = search_area.rfind(sep, target_size // 2, target_size + len(sep))
            if last_idx != -1:
                best_point = last_idx + len(sep)
                break

        return min(best_point, len(text))


# ========================== 3. 语义分块 ==========================

class SemanticChunker(BaseChunker):
    """
    语义分块
    基于段落和句子边界进行分割，保持语义完整性
    """

    name = "semantic"
    description = "按段落和句子语义边界合并，保持语义完整"

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        chunk_size = self._get_param(kwargs, "chunk_size", settings.CHUNK_SIZE)
        chunk_overlap = self._get_param(kwargs, "chunk_overlap", settings.CHUNK_OVERLAP)

        # 段落分割
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return []

        chunks: List[TextChunk] = []
        current_buffer = []
        current_len = 0
        index = 0
        global_pos = 0

        def flush_buffer():
            nonlocal current_buffer, current_len, index, global_pos
            if not current_buffer:
                return
            content = "\n\n".join(current_buffer)
            end_pos = global_pos + len(content)
            chunks.append(
                TextChunk(
                    content=content,
                    index=index,
                    start_pos=global_pos,
                    end_pos=end_pos,
                    metadata={"strategy": self.name, "char_count": len(content)},
                )
            )
            # 重叠处理
            if chunk_overlap > 0 and len(current_buffer) > 1:
                overlap_text = current_buffer[-1]
                current_buffer = [overlap_text]
                current_len = len(overlap_text)
            else:
                current_buffer = []
                current_len = 0
            index += 1
            global_pos = end_pos - (len(current_buffer[0]) if current_buffer else 0)

        for para in paragraphs:
            para_len = len(para)
            # 单个段落超过 chunk_size，需要句子级分割
            if para_len > chunk_size:
                if current_buffer:
                    flush_buffer()
                sentences = re.split(r"(?<=[。！？.!?])\s+", para)
                for sent in sentences:
                    if current_len + len(sent) > chunk_size and current_buffer:
                        flush_buffer()
                    current_buffer.append(sent)
                    current_len += len(sent) + 1
            else:
                if current_len + para_len > chunk_size and current_buffer:
                    flush_buffer()
                current_buffer.append(para)
                current_len += para_len + 2

        if current_buffer:
            content = "\n\n".join(current_buffer)
            chunks.append(
                TextChunk(
                    content=content,
                    index=index,
                    start_pos=global_pos,
                    end_pos=global_pos + len(content),
                    metadata={"strategy": self.name, "char_count": len(content)},
                )
            )

        return chunks


# ========================== 4. 结构分块 ==========================

class StructuredChunker(BaseChunker):
    """
    结构分块
    按文档结构（标题层级、表格、段落）进行分块
    需要输入结构化元素列表
    """

    name = "structured"
    description = "按标题层级、表格、列表等文档结构切分"

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        chunk_size = self._get_param(kwargs, "chunk_size", settings.CHUNK_SIZE)
        heading_levels = self._get_param(kwargs, "heading_levels", [1, 2, 3])
        preserve_tables = self._get_param(kwargs, "preserve_tables", True)
        structured_elements = self._get_param(kwargs, "structured_elements", None)

        # 如果没有结构化元素，尝试从文本中提取
        if structured_elements is None:
            structured_elements = self._extract_structure(text)

        chunks: List[TextChunk] = []
        index = 0
        current_section = []
        current_title = ""
        current_level = 0
        current_start = 0

        for elem in structured_elements:
            elem_type = elem.get("type", "text")
            elem_text = elem.get("text", "").strip()
            if not elem_text:
                continue

            # 标题：作为新 section 的开始
            if elem_type == "heading":
                level = elem.get("level", 1)
                # 保存当前 section
                if current_section:
                    content = "\n\n".join(current_section).strip()
                    if content:
                        chunks.append(
                            TextChunk(
                                content=content,
                                index=index,
                                start_pos=current_start,
                                end_pos=current_start + len(content),
                                metadata={
                                    "strategy": self.name,
                                    "section_title": current_title,
                                    "heading_level": current_level,
                                    "char_count": len(content),
                                },
                            )
                        )
                        index += 1

                current_title = elem_text
                current_level = level
                current_section = [elem_text]
                current_start = text.find(elem_text, current_start)

            # 表格：根据 preserve_tables 决定是否单独成块
            elif elem_type == "table" and preserve_tables:
                if current_section:
                    content = "\n\n".join(current_section).strip()
                    if content:
                        chunks.append(
                            TextChunk(
                                content=content,
                                index=index,
                                start_pos=current_start,
                                end_pos=current_start + len(content),
                                metadata={
                                    "strategy": self.name,
                                    "section_title": current_title,
                                    "heading_level": current_level,
                                    "char_count": len(content),
                                },
                            )
                        )
                        index += 1

                chunks.append(
                    TextChunk(
                        content=elem_text,
                        index=index,
                        start_pos=text.find(elem_text, current_start),
                        end_pos=text.find(elem_text, current_start) + len(elem_text),
                        metadata={
                            "strategy": self.name,
                            "section_title": current_title,
                            "heading_level": current_level,
                            "element_type": "table",
                            "char_count": len(elem_text),
                        },
                    )
                )
                index += 1
                current_section = []

            else:
                current_section.append(elem_text)
                # 如果当前 section 超过 chunk_size，切分
                combined = "\n\n".join(current_section)
                if len(combined) > chunk_size:
                    content = "\n\n".join(current_section[:-1]).strip()
                    if content:
                        chunks.append(
                            TextChunk(
                                content=content,
                                index=index,
                                start_pos=current_start,
                                end_pos=current_start + len(content),
                                metadata={
                                    "strategy": self.name,
                                    "section_title": current_title,
                                    "heading_level": current_level,
                                    "char_count": len(content),
                                },
                            )
                        )
                        index += 1
                    current_section = [current_section[-1]]
                    current_start = text.find(current_section[0], current_start)

        # 处理剩余
        if current_section:
            content = "\n\n".join(current_section).strip()
            if content:
                chunks.append(
                    TextChunk(
                        content=content,
                        index=index,
                        start_pos=current_start,
                        end_pos=current_start + len(content),
                        metadata={
                            "strategy": self.name,
                            "section_title": current_title,
                            "heading_level": current_level,
                            "char_count": len(content),
                        },
                    )
                )

        return chunks

    def _extract_structure(self, text: str) -> List[Dict]:
        """从纯文本中启发式提取结构元素"""
        elements = []
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Markdown 标题
            md_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if md_match:
                level = len(md_match.group(1))
                elements.append({"type": "heading", "level": level, "text": md_match.group(2)})
                continue

            # 数字标题（如 "1. 标题"、"1.1 标题"）
            num_match = re.match(r"^(\d+(?:\.\d+)*)\s*[.、)）]\s*(.+)$", line)
            if num_match:
                level = num_match.group(1).count(".") + 1
                elements.append({"type": "heading", "level": min(level, 6), "text": line})
                continue

            # 短行 + 全大写/粗体特征（可能是标题）
            if len(line) < 50 and (line.isupper() or re.match(r"^【(.+)】$", line)):
                elements.append({"type": "heading", "level": 2, "text": line})
                continue

            # 表格特征（包含 | 或制表符）
            if "|" in line or "\t" in line:
                elements.append({"type": "table_row", "text": line})
                continue

            elements.append({"type": "paragraph", "text": line})

        # 合并连续的表格行
        merged = []
        table_buffer = []
        for elem in elements:
            if elem["type"] == "table_row":
                table_buffer.append(elem["text"])
            else:
                if table_buffer:
                    merged.append({"type": "table", "text": "\n".join(table_buffer)})
                    table_buffer = []
                merged.append(elem)
        if table_buffer:
            merged.append({"type": "table", "text": "\n".join(table_buffer)})

        return merged


# ========================== 5. 父子分块 ==========================

class ParentChildChunker(BaseChunker):
    """
    父子分块
    父块 = 大段上下文（如整节），用于提供完整上下文
    子块 = 小片段，用于精确检索
    两种块都输出，metadata 中标记 parent_id 关系
    """

    name = "parent_child"
    description = "父块提供完整上下文，子块用于精确检索"

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        parent_size = self._get_param(kwargs, "parent_chunk_size", getattr(settings, "PARENT_CHUNK_SIZE", 2048))
        child_size = self._get_param(kwargs, "child_chunk_size", getattr(settings, "CHILD_CHUNK_SIZE", 256))
        parent_overlap = self._get_param(kwargs, "parent_overlap", getattr(settings, "PARENT_CHUNK_OVERLAP", 256))
        child_overlap = self._get_param(kwargs, "child_overlap", getattr(settings, "CHILD_CHUNK_OVERLAP", 64))

        # 第一步：生成父块（使用语义分块策略，更大的块）
        semantic_chunker = SemanticChunker()
        parent_chunks = semantic_chunker.chunk(
            text,
            chunk_size=parent_size,
            chunk_overlap=parent_overlap,
        )

        all_chunks: List[TextChunk] = []
        child_index = 0

        for parent in parent_chunks:
            parent_id = f"parent_{uuid.uuid4().hex[:8]}"
            parent_content = parent.content

            # 父块
            parent_chunk = TextChunk(
                content=parent_content,
                index=child_index,
                start_pos=parent.start_pos,
                end_pos=parent.end_pos,
                metadata={
                    "strategy": self.name,
                    "chunk_type": "parent",
                    "parent_id": None,
                    "char_count": len(parent_content),
                },
            )
            all_chunks.append(parent_chunk)
            child_index += 1

            # 第二步：将父块内容细分为子块
            if len(parent_content) <= child_size:
                # 父块本身就不大，作为一个子块
                child_chunk = TextChunk(
                    content=parent_content,
                    index=child_index,
                    start_pos=parent.start_pos,
                    end_pos=parent.end_pos,
                    metadata={
                        "strategy": self.name,
                        "chunk_type": "child",
                        "parent_id": parent_id,
                        "char_count": len(parent_content),
                    },
                )
                all_chunks.append(child_chunk)
                child_index += 1
            else:
                # 用递归分块策略细分父块
                recursive_chunker = RecursiveChunker()
                child_chunks = recursive_chunker.chunk(
                    parent_content,
                    chunk_size=child_size,
                    chunk_overlap=child_overlap,
                )
                for cc in child_chunks:
                    child_chunk = TextChunk(
                        content=cc.content,
                        index=child_index,
                        start_pos=parent.start_pos + cc.start_pos,
                        end_pos=parent.start_pos + cc.end_pos,
                        metadata={
                            "strategy": self.name,
                            "chunk_type": "child",
                            "parent_id": parent_id,
                            "char_count": len(cc.content),
                        },
                    )
                    all_chunks.append(child_chunk)
                    child_index += 1

            # 更新父块的 parent_id（自引用）
            parent_chunk.metadata["parent_id"] = parent_id

        return all_chunks


# ========================== 6. LLM 智能分块 ==========================

class LLMSmartChunker(BaseChunker):
    """
    LLM 智能分块
    调用大模型分析文档结构，按语义边界智能分块
    """

    name = "llm_smart"
    description = "调用大模型分析文档结构智能分块"

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        # 同步调用不支持 async，这里返回一个同步实现
        # 实际使用时，ChunkingEngine 会提供 async_chunk 方法
        model = self._get_param(kwargs, "model", getattr(settings, "LLM_CHUNK_MODEL", "kimi-k2.6"))
        temperature = self._get_param(kwargs, "temperature", getattr(settings, "LLM_CHUNK_TEMPERATURE", 0.3))
        max_tokens = self._get_param(kwargs, "max_tokens", getattr(settings, "LLM_CHUNK_MAX_TOKENS", 4096))

        # 如果文本太长，先粗分再逐段调用 LLM
        max_input_chars = 8000
        if len(text) > max_input_chars:
            # 先用语义分块粗分
            semantic = SemanticChunker()
            coarse_chunks = semantic.chunk(text, chunk_size=max_input_chars, chunk_overlap=200)

            all_chunks: List[TextChunk] = []
            for i, coarse in enumerate(coarse_chunks):
                sub_chunks = self._llm_chunk_sync(
                    coarse.content,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                for j, sc in enumerate(sub_chunks):
                    all_chunks.append(
                        TextChunk(
                            content=sc["content"],
                            index=len(all_chunks),
                            start_pos=coarse.start_pos,
                            end_pos=coarse.end_pos,
                            metadata={
                                "strategy": self.name,
                                "char_count": len(sc["content"]),
                                "reason": sc.get("reason", ""),
                                "coarse_index": i,
                            },
                        )
                    )
            return all_chunks
        else:
            sub_chunks = self._llm_chunk_sync(
                text,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return [
                TextChunk(
                    content=sc["content"],
                    index=i,
                    start_pos=0,
                    end_pos=len(text),
                    metadata={
                        "strategy": self.name,
                        "char_count": len(sc["content"]),
                        "reason": sc.get("reason", ""),
                    },
                )
                for i, sc in enumerate(sub_chunks)
            ]

    def _llm_chunk_sync(self, text: str, model: str, temperature: float, max_tokens: int) -> List[Dict]:
        """同步调用 LLM 进行分块（fallback 到语义分块）"""
        import httpx

        api_key = settings.BAICHUAN_API_KEY
        base_url = settings.BAICHUAN_BASE_URL

        if not api_key:
            logger.warning("LLM 智能分块：百炼 API Key 未配置，降级为语义分块")
            semantic = SemanticChunker()
            chunks = semantic.chunk(text, chunk_size=512, chunk_overlap=128)
            return [{"content": c.content, "reason": "API未配置，降级语义分块"} for c in chunks]

        prompt = (
            "你是一个文档分块专家。请分析以下文本，按语义边界将其分割为若干块。"
            "每个块应包含一个完整的语义单元（如一个主题、一个段落、一个观点）。\n\n"
            "要求：\n"
            "1. 每块长度在 200-800 字符之间\n"
            "2. 不要在句子中间切断\n"
            "3. 保持上下文连贯性\n"
            "4. 输出严格的 JSON 格式数组\n\n"
            "输出格式示例：\n"
            '[{"content": "块1内容", "reason": "这是一个完整的主题"}, '
            '{"content": "块2内容", "reason": "另一个独立观点"}]\n\n'
            f"文本内容（{len(text)} 字符）：\n{text}"
        )

        try:
            client = httpx.Client(timeout=120.0)
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个文档分块专家，擅长按语义边界分割文本。只输出 JSON 格式。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 提取 JSON
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                chunks = json.loads(json_match.group())
                if isinstance(chunks, list) and len(chunks) > 0:
                    logger.info(f"LLM 智能分块成功: 生成 {len(chunks)} 个块")
                    return chunks

            logger.warning("LLM 智能分块：无法解析返回结果，降级为语义分块")
        except Exception as e:
            logger.warning(f"LLM 智能分块失败: {e}，降级为语义分块")

        # 降级到语义分块
        semantic = SemanticChunker()
        chunks = semantic.chunk(text, chunk_size=512, chunk_overlap=128)
        return [{"content": c.content, "reason": "LLM调用失败，降级语义分块"} for c in chunks]


# ========================== 分块引擎统一入口 ==========================

class ChunkingEngine:
    """
    分块引擎统一入口
    支持多种分块策略，支持自动选择
    """

    STRATEGIES = {
        "fixed_size": FixedSizeChunker,
        "recursive": RecursiveChunker,
        "semantic": SemanticChunker,
        "structured": StructuredChunker,
        "parent_child": ParentChildChunker,
        "llm_smart": LLMSmartChunker,
    }

    def __init__(self):
        self._chunkers: Dict[str, BaseChunker] = {}
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP

    def _get_chunker(self, strategy: str) -> BaseChunker:
        """获取或创建分块器实例"""
        if strategy not in self._chunkers:
            if strategy not in self.STRATEGIES:
                raise ValueError(f"未知的分块策略: {strategy}，支持: {list(self.STRATEGIES.keys())}")
            self._chunkers[strategy] = self.STRATEGIES[strategy]()
        return self._chunkers[strategy]

    def chunk(
        self,
        text: str,
        strategy: Literal["auto", "fixed_size", "recursive", "semantic", "structured", "parent_child", "llm_smart"] = "auto",
        **kwargs,
    ) -> List[TextChunk]:
        """
        对文本进行分块
        :param text: 原始文本
        :param strategy: 分块策略
        :param kwargs: 策略特定参数
        """
        if strategy == "auto":
            strategy = self._auto_select_strategy(text)
            logger.info(f"自动选择分块策略: {strategy}")

        chunker = self._get_chunker(strategy)
        chunks = chunker.chunk(text, **kwargs)

        # 统一后处理：确保索引连续、补充统计信息
        for i, ch in enumerate(chunks):
            ch.index = i
            ch.metadata.setdefault("strategy", strategy)
            ch.metadata.setdefault("char_count", len(ch.content))

        logger.info(f"分块完成 [{strategy}]: 共 {len(chunks)} 个 chunks")
        return chunks

    def _auto_select_strategy(self, text: str) -> str:
        """
        自动选择最优分块策略
        - 包含明确标题结构 -> 结构分块
        - 短文本 -> 语义分块
        - 长文本/代码密集 -> 递归分块
        - 表格/列表密集 -> 固定大小
        """
        text_len = len(text)
        newline_ratio = text.count("\n") / max(text_len, 1)
        heading_count = len(re.findall(r"^(#{1,6}\s+|\d+\.\d*\s+[\u4e00-\u9fa5])", text, re.MULTILINE))
        table_count = text.count("|") + text.count("\t")

        # 标题丰富 -> 结构分块
        if heading_count >= 3 and newline_ratio > 0.03:
            return "structured"

        # 表格密集 -> 固定大小
        if table_count > text_len * 0.1:
            return "fixed_size"

        # 短文本 -> 语义分块
        if text_len < 2000:
            return "semantic"

        # 换行丰富 -> 语义分块
        if newline_ratio > 0.05:
            return "semantic"

        # 默认递归分块
        return "recursive"

    def get_strategy_info(self) -> List[Dict]:
        """获取所有策略的信息（用于前端展示）"""
        return [
            {
                "name": key,
                "description": cls.description,
            }
            for key, cls in self.STRATEGIES.items()
        ]


# ========================== 全局单例 ==========================

_chunking_engine: ChunkingEngine | None = None


def get_chunking_engine() -> ChunkingEngine:
    global _chunking_engine
    if _chunking_engine is None:
        _chunking_engine = ChunkingEngine()
    return _chunking_engine
