"""
阿里云百炼文档解析 Fallback
当本地 Unstructured 无法解析某种格式时，调用百炼 API 提取文档文本。
支持：PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, CSV, JSON, EPUB 等
"""
import base64
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class BaichuanParser:
    """
    百炼文档解析器
    - 文本类文件：直接读取后发送给模型做清洗/结构化
    - 二进制文件：base64 编码后发送给模型提取文本
    """

    TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".xml", ".yaml", ".yml"}

    def __init__(self):
        self.api_key = settings.BAICHUAN_API_KEY
        self.model = settings.BAICHUAN_MODEL
        self.base_url = settings.BAICHUAN_BASE_URL
        self.max_file_size = settings.BAICHUAN_MAX_FILE_SIZE
        self._client = httpx.AsyncClient(timeout=120.0)

    async def parse(self, file_path: str | Path, filename: Optional[str] = None) -> str:
        """
        调用百炼 API 解析文档
        :param file_path: 本地文件路径
        :param filename: 原始文件名（用于判断类型）
        :return: 提取的纯文本
        """
        file_path = Path(file_path)
        filename = filename or file_path.name
        ext = Path(filename).suffix.lower()

        # 检查文件大小
        file_size = file_path.stat().st_size
        if file_size > self.max_file_size:
            raise ValueError(f"文件 {filename} 大小 {file_size / 1024 / 1024:.2f}MB 超过百炼限制 {self.max_file_size / 1024 / 1024}MB")

        if not self.api_key:
            raise ValueError("百炼 API Key 未配置，无法使用 fallback 解析")

        logger.info(f"使用百炼 API 解析文档: {filename} ({file_size} bytes)")

        # 文本类文件：直接读取文本
        if ext in self.TEXT_EXTENSIONS:
            return await self._parse_text_file(file_path, filename)

        # 二进制文件：base64 编码后发送
        return await self._parse_binary_file(file_path, filename)

    async def _parse_text_file(self, file_path: Path, filename: str) -> str:
        """解析文本类文件"""
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="utf-8", errors="ignore")

        # 截断过长的文本（控制 token 数量）
        max_chars = 50000
        truncated = len(text) > max_chars
        text_to_send = text[:max_chars]

        prompt = (
            f"请整理以下 {filename} 文件的文本内容，要求：\n"
            f"1. 保持原有的段落和标题结构\n"
            f"2. 去除乱码、多余空白和无意义的符号\n"
            f"3. 保留所有实质性内容\n"
            f"4. 直接输出整理后的文本，不要添加额外说明\n\n"
            f"{'(内容已截断，仅处理前 ' + str(max_chars) + ' 字符)' if truncated else ''}\n"
            f"{text_to_send}"
        )

        return await self._call_api(prompt, filename)

    async def _parse_binary_file(self, file_path: Path, filename: str) -> str:
        """解析二进制文件（base64 编码）"""
        content = file_path.read_bytes()
        b64 = base64.b64encode(content).decode("utf-8")

        # 截断 base64 字符串（控制 token 数量，base64 约为原大小的 4/3）
        max_b64_chars = 300000  # 约 225KB 原始数据
        truncated = len(b64) > max_b64_chars
        b64_to_send = b64[:max_b64_chars]

        prompt = (
            f"以下是一个 {filename} 文件的 base64 编码内容。\n"
            f"请解码并提取其中的所有文本内容，要求：\n"
            f"1. 保持原有的段落和标题结构\n"
            f"2. 去除乱码、多余空白和无意义的符号\n"
            f"3. 保留所有实质性内容\n"
            f"4. 直接输出提取的文本，不要添加额外说明\n\n"
            f"{'(内容已截断，仅处理前 ' + str(max_b64_chars) + ' 字符 base64)' if truncated else ''}\n"
            f"{b64_to_send}"
        )

        return await self._call_api(prompt, filename)

    async def _call_api(self, prompt: str, filename: str) -> str:
        """调用百炼 API"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的文档解析助手，擅长从各种格式文件中提取结构化纯文本。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        try:
            resp = await self._client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content.strip():
                raise ValueError("百炼 API 返回空内容")
            logger.info(f"百炼解析完成: {filename}, 输出 {len(content)} 字符")
            return content
        except httpx.HTTPStatusError as e:
            logger.error(f"百炼 API 请求失败: {e.response.status_code} {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"百炼解析异常: {e}")
            raise

    async def close(self):
        await self._client.aclose()


# 全局单例
_baichuan_parser: BaichuanParser | None = None


def get_baichuan_parser() -> BaichuanParser:
    global _baichuan_parser
    if _baichuan_parser is None:
        _baichuan_parser = BaichuanParser()
    return _baichuan_parser
