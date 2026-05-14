"""
文档解析模块
基于 Unstructured 实现多格式文档解析 + 文本清洗
支持: PDF, DOCX, TXT, MD, HTML, PPTX, XLSX, CSV, JSON, EPUB 等
Fallback: 当 Unstructured 失败时，调用百炼 API
"""
import csv
import json
import re
from pathlib import Path
from typing import List, Optional

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class ParsedDocument:
    """解析后的文档对象"""

    def __init__(
        self,
        filename: str,
        text: str,
        pages: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ):
        self.filename = filename
        self.text = text
        self.pages = pages or []
        self.metadata = metadata or {}
        self.file_type = Path(filename).suffix.lower()

    @property
    def is_empty(self) -> bool:
        return not self.text or not self.text.strip()


class DocumentParser:
    """
    文档解析器
    自动识别文件类型，调用对应的解析策略
    Fallback 链：Unstructured → 纯Python库 → 百炼API → 纯文本兜底
    """

    # 明确支持的格式映射
    SUPPORTED_FORMATS = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "doc",
        ".txt": "text",
        ".md": "text",
        ".markdown": "text",
        ".html": "html",
        ".htm": "html",
        ".pptx": "pptx",
        ".ppt": "pptx",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".csv": "csv",
        ".json": "json",
        ".epub": "epub",
        ".xml": "text",
        ".yaml": "text",
        ".yml": "text",
    }

    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def parse(self, file_path: str | Path, filename: Optional[str] = None) -> ParsedDocument:
        """
        解析文档主入口
        :param file_path: 本地文件路径
        :param filename: 原始文件名（用于类型判断）
        """
        file_path = Path(file_path)
        filename = filename or file_path.name
        ext = Path(filename).suffix.lower()
        doc_type = self.SUPPORTED_FORMATS.get(ext, "unknown")

        logger.info(f"开始解析文档: {filename} (类型: {ext} -> {doc_type})")

        # 1. 尝试本地 Unstructured 解析
        try:
            return await self._parse_local(file_path, filename, doc_type)
        except ImportError as e:
            logger.warning(f"Unstructured 缺少依赖 [{doc_type}]: {e}")
        except Exception as e:
            logger.warning(f"Unstructured 解析失败 [{doc_type}]: {e}")

        # 2. 尝试纯 Python 库 fallback
        try:
            return await self._parse_pure_python(file_path, filename, doc_type)
        except ImportError as e:
            logger.warning(f"纯 Python 库缺少依赖 [{doc_type}]: {e}")
        except Exception as e:
            logger.warning(f"纯 Python 库解析失败 [{doc_type}]: {e}")

        # 3. 尝试百炼 API fallback
        try:
            from app.core.baichuan_parser import get_baichuan_parser

            if settings.BAICHUAN_API_KEY:
                baichuan = get_baichuan_parser()
                text = await baichuan.parse(file_path, filename)
                return ParsedDocument(
                    filename=filename,
                    text=self._clean_text(text),
                    metadata={"file_type": doc_type, "parser": "baichuan_api"},
                )
        except Exception as e:
            logger.warning(f"百炼 API 解析失败: {e}")

        # 4. 纯文本兜底
        try:
            return await self._parse_text_fallback(file_path, filename)
        except Exception as e:
            logger.error(f"所有解析方式均失败 {filename}: {e}")
            raise ValueError(f"无法解析文件 {filename}: {e}")

    async def _parse_local(self, file_path: Path, filename: str, doc_type: str) -> ParsedDocument:
        """使用 Unstructured 本地解析"""
        if doc_type == "pdf":
            return await self._parse_pdf(file_path, filename)
        elif doc_type == "docx":
            return await self._parse_docx(file_path, filename)
        elif doc_type == "text":
            return await self._parse_text(file_path, filename)
        elif doc_type == "html":
            return await self._parse_html(file_path, filename)
        elif doc_type == "pptx":
            return await self._parse_pptx(file_path, filename)
        elif doc_type == "xlsx":
            return await self._parse_xlsx_unstructured(file_path, filename)
        elif doc_type == "csv":
            return await self._parse_csv(file_path, filename)
        elif doc_type == "json":
            return await self._parse_json(file_path, filename)
        elif doc_type == "epub":
            return await self._parse_epub(file_path, filename)
        else:
            raise ValueError(f"Unstructured 不支持的格式: {doc_type}")

    async def _parse_pure_python(self, file_path: Path, filename: str, doc_type: str) -> ParsedDocument:
        """纯 Python 库 fallback"""
        if doc_type == "pdf":
            return await self._parse_pdf_pymupdf(file_path, filename)
        elif doc_type == "docx":
            return await self._parse_docx_python(file_path, filename)
        elif doc_type == "xlsx":
            return await self._parse_xlsx_openpyxl(file_path, filename)
        elif doc_type == "pptx":
            return await self._parse_pptx_python(file_path, filename)
        elif doc_type == "epub":
            return await self._parse_epub_ebooklib(file_path, filename)
        else:
            raise ValueError(f"无纯 Python fallback: {doc_type}")

    # ==================== Unstructured 解析 ====================

    async def _parse_pdf(self, file_path: Path, filename: str) -> ParsedDocument:
        from unstructured.partition.pdf import partition_pdf

        # 根据文件大小选择策略
        file_size = file_path.stat().st_size
        strategy = "fast" if file_size < 1024 * 1024 else "auto"

        elements = partition_pdf(
            filename=str(file_path),
            strategy=strategy,
            include_page_breaks=True,
        )
        pages = self._elements_to_pages(elements)
        full_text = "\n\n".join(pages)
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(full_text),
            pages=[self._clean_text(p) for p in pages],
            metadata={"file_type": "pdf", "page_count": len(pages), "strategy": strategy},
        )

    async def _parse_docx(self, file_path: Path, filename: str) -> ParsedDocument:
        from unstructured.partition.docx import partition_docx

        elements = partition_docx(filename=str(file_path))
        text = "\n".join([str(el) for el in elements])
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "docx"},
        )

    async def _parse_text(self, file_path: Path, filename: str) -> ParsedDocument:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(content),
            metadata={"file_type": Path(filename).suffix.lower().lstrip(".")},
        )

    async def _parse_html(self, file_path: Path, filename: str) -> ParsedDocument:
        from unstructured.partition.html import partition_html

        elements = partition_html(filename=str(file_path))
        text = "\n".join([str(el) for el in elements])
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "html"},
        )

    async def _parse_pptx(self, file_path: Path, filename: str) -> ParsedDocument:
        from unstructured.partition.pptx import partition_pptx

        elements = partition_pptx(filename=str(file_path))
        text = "\n".join([str(el) for el in elements])
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "pptx"},
        )

    async def _parse_xlsx_unstructured(self, file_path: Path, filename: str) -> ParsedDocument:
        from unstructured.partition.xlsx import partition_xlsx

        elements = partition_xlsx(filename=str(file_path))
        text = "\n".join([str(el) for el in elements])
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "xlsx"},
        )

    async def _parse_csv(self, file_path: Path, filename: str) -> ParsedDocument:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        # 用 csv 模块读取，增强格式
        lines = []
        try:
            reader = csv.reader(text.splitlines())
            for row in reader:
                lines.append(" | ".join(row))
        except Exception:
            lines = text.splitlines()
        return ParsedDocument(
            filename=filename,
            text=self._clean_text("\n".join(lines)),
            metadata={"file_type": "csv"},
        )

    async def _parse_json(self, file_path: Path, filename: str) -> ParsedDocument:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            data = json.loads(content)
            # 将 JSON 转为可读文本
            text = json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            text = content
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "json"},
        )

    async def _parse_epub(self, file_path: Path, filename: str) -> ParsedDocument:
        from unstructured.partition.epub import partition_epub

        elements = partition_epub(filename=str(file_path))
        text = "\n".join([str(el) for el in elements])
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "epub"},
        )

    # ==================== 纯 Python Fallback ====================

    async def _parse_pdf_pymupdf(self, file_path: Path, filename: str) -> ParsedDocument:
        """PyMuPDF (fitz) 解析 PDF"""
        import fitz  # PyMuPDF

        doc = fitz.open(str(file_path))
        pages = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            pages.append(text)
        doc.close()
        full_text = "\n\n".join(pages)
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(full_text),
            pages=[self._clean_text(p) for p in pages],
            metadata={"file_type": "pdf", "page_count": len(pages), "parser": "pymupdf"},
        )

    async def _parse_docx_python(self, file_path: Path, filename: str) -> ParsedDocument:
        """python-docx 解析 DOCX"""
        from docx import Document

        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": "docx", "parser": "python-docx"},
        )

    async def _parse_xlsx_openpyxl(self, file_path: Path, filename: str) -> ParsedDocument:
        """openpyxl 解析 XLSX"""
        from openpyxl import load_workbook

        wb = load_workbook(str(file_path), data_only=True)
        lines = []
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            lines.append(f"--- Sheet: {sheet_name} ---")
            for row in sheet.iter_rows(values_only=True):
                row_text = " | ".join(str(cell) if cell is not None else "" for cell in row)
                if row_text.strip():
                    lines.append(row_text)
        wb.close()
        return ParsedDocument(
            filename=filename,
            text=self._clean_text("\n".join(lines)),
            metadata={"file_type": "xlsx", "parser": "openpyxl"},
        )

    async def _parse_pptx_python(self, file_path: Path, filename: str) -> ParsedDocument:
        """python-pptx 解析 PPTX"""
        from pptx import Presentation

        prs = Presentation(str(file_path))
        lines = []
        for i, slide in enumerate(prs.slides, 1):
            lines.append(f"--- Slide {i} ---")
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    lines.append(shape.text.strip())
        return ParsedDocument(
            filename=filename,
            text=self._clean_text("\n".join(lines)),
            metadata={"file_type": "pptx", "parser": "python-pptx"},
        )

    async def _parse_epub_ebooklib(self, file_path: Path, filename: str) -> ParsedDocument:
        """ebooklib 解析 EPUB"""
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(str(file_path))
        lines = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text = soup.get_text(separator="\n")
                lines.append(text)
        return ParsedDocument(
            filename=filename,
            text=self._clean_text("\n".join(lines)),
            metadata={"file_type": "epub", "parser": "ebooklib"},
        )

    # ==================== 文本兜底 ====================

    async def _parse_text_fallback(self, file_path: Path, filename: str) -> ParsedDocument:
        """最后的兜底：尝试当作文本读取"""
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            # 二进制文件，尝试读取可打印字符
            content = file_path.read_bytes()
            text = "".join(chr(b) if 32 <= b < 127 or b in (10, 13) else " " for b in content)

        return ParsedDocument(
            filename=filename,
            text=self._clean_text(text),
            metadata={"file_type": Path(filename).suffix.lower().lstrip("."), "parser": "text_fallback"},
        )

    # ==================== 工具方法 ====================

    def _elements_to_pages(self, elements) -> List[str]:
        """将 unstructured elements 按页分组"""
        pages: List[List[str]] = []
        current_page: List[str] = []
        current_page_num = 1

        for el in elements:
            page_num = getattr(el.metadata, "page_number", current_page_num)
            if page_num != current_page_num and current_page:
                pages.append("\n".join(current_page))
                current_page = []
                current_page_num = page_num
            current_page.append(str(el))

        if current_page:
            pages.append("\n".join(current_page))
        return pages

    def _clean_text(self, text: str) -> str:
        """
        文本清洗：
        - 去除多余空白
        - 统一换行符
        - 去除乱码控制字符
        """
        # 统一换行
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 去除控制字符（保留换行和制表符）
        text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) != 127))
        # 去除多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 去除行首行尾空格
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)
        return text.strip()

    def save_upload(self, content: bytes, filename: str) -> Path:
        """保存上传的文件到本地"""
        import uuid

        safe_name = f"{uuid.uuid4().hex}_{filename}"
        file_path = self.upload_dir / safe_name
        file_path.write_bytes(content)
        return file_path


# 全局单例
_parser: DocumentParser | None = None


def get_parser() -> DocumentParser:
    global _parser
    if _parser is None:
        _parser = DocumentParser()
    return _parser
