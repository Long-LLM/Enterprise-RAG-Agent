"""
全局配置管理 - Pydantic Settings
支持 .env 文件加载，所有配置项均可通过环境变量覆盖
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple, Type

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# 定位项目根目录的 .env 文件（config.py 位于 backend/app/）
_ENV_FILE = Path(__file__).parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        自定义配置源优先级：
        .env 文件 > 环境变量 > 代码默认值
        这样 .env 里的配置不会被系统环境变量意外覆盖
        """
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            file_secret_settings,
        )

    # --- App ---
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    UPLOAD_DIR: str = "./uploads"
    LOG_LEVEL: str = "INFO"

    # --- Security ---
    # JWT 签名密钥，生产环境必须修改，长度 >= 32
    SECRET_KEY: str = "enterprise-rag-agent-secret-key-change-me"

    # --- Milvus ---
    MILVUS_HOST: str = "192.168.184.128"
    MILVUS_PORT: str = "19530"
    MILVUS_DB_NAME: str = "default"
    MILVUS_COLLECTION_NAME: str = "wolin_docs"
    MILVUS_TOKEN: Optional[str] = None

    # --- Embedding (Ollama) ---
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "bge-m3"
    EMBED_DIM: int = 1024

    # --- LLM ---
    LLM_PROVIDER: str = "ollama"  # "ollama" | "vllm"
    OLLAMA_LLM_MODEL: str = "qwen2.5:7b-instruct"

    # vLLM 预留
    VLLM_API_URL: Optional[str] = None
    VLLM_MODEL: Optional[str] = None
    VLLM_API_KEY: Optional[str] = None

    # --- 百炼文档解析 Fallback ---
    BAICHUAN_API_KEY: Optional[str] = None
    BAICHUAN_MODEL: str = "kimi-k2.6"
    BAICHUAN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    BAICHUAN_MAX_FILE_SIZE: int = 5 * 1024 * 1024  # 5MB

    # --- Metadata DB ---
    # SQLite for dev, PostgreSQL for production via docker-compose
    # Format: postgresql+asyncpg://user:pass@host:port/db
    METADATA_DB_URL: str = "sqlite+aiosqlite:///./metadata.db"

    # --- Chunking ---
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 128
    DEFAULT_CHUNK_STRATEGY: str = "auto"
    CHUNK_PREVIEW_MAX_CHARS: int = 30000

    # --- Parent-Child Chunking ---
    PARENT_CHUNK_SIZE: int = 2048
    CHILD_CHUNK_SIZE: int = 256
    PARENT_CHUNK_OVERLAP: int = 256
    CHILD_CHUNK_OVERLAP: int = 64

    # --- LLM Chunking ---
    LLM_CHUNK_MODEL: str = "kimi-k2.6"
    LLM_CHUNK_TEMPERATURE: float = 0.3
    LLM_CHUNK_MAX_TOKENS: int = 4096

    # --- Retrieval ---
    TOP_K_VECTOR: int = 10
    TOP_K_BM25: int = 10
    TOP_K_RERANK: int = 5
    RERANKER_MODEL: str = "BAAI/bge-reranker-base"

    @property
    def milvus_uri(self) -> str:
        return f"http://{self.MILVUS_HOST}:{self.MILVUS_PORT}"

    @property
    def ollama_embed_url(self) -> str:
        return f"{self.OLLAMA_HOST}/api/embed"

    @property
    def ollama_chat_url(self) -> str:
        return f"{self.OLLAMA_HOST}/api/chat"

    @property
    def ollama_generate_url(self) -> str:
        return f"{self.OLLAMA_HOST}/api/generate"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
