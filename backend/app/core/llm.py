"""
LLM 服务统一接口层
当前：Ollama 本地 qwen2.5:7b-instruct
未来：无缝切换 vLLM（通过配置 LLM_PROVIDER=vllm）
"""
import json
import time
from typing import AsyncIterator, List, Optional

import httpx

from app.config import Settings, get_settings
from app.core.metrics import LLM_DURATION, LLM_REQUESTS, LLM_TOKENS_GENERATED
from app.logger import get_logger

logger = get_logger(__name__)


class ChatMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def dict(self):
        return {"role": self.role, "content": self.content}


class LLMService:
    """
    LLM 统一调用接口
    - 支持 Ollama 和 vLLM 两种 Provider
    - 支持普通调用与流式输出（SSE）
    - 支持系统提示词注入
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.provider = self.settings.LLM_PROVIDER.lower()
        self._client = httpx.AsyncClient(timeout=300.0)

        # Ollama 配置
        self.ollama_model = self.settings.OLLAMA_LLM_MODEL
        self.ollama_chat_url = self.settings.ollama_chat_url
        self.ollama_generate_url = self.settings.ollama_generate_url

        # vLLM 配置（预留）
        self.vllm_api_url = self.settings.VLLM_API_URL
        self.vllm_model = self.settings.VLLM_MODEL
        self.vllm_api_key = self.settings.VLLM_API_KEY

    async def chat(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
    ) -> str:
        """
        非流式对话调用，返回完整回复文本
        """
        start = time.time()
        status = "success"
        try:
            if self.provider == "ollama":
                result = await self._chat_ollama(messages, system_prompt, temperature, max_tokens, stream=False)
            elif self.provider == "vllm":
                result = await self._chat_vllm(messages, system_prompt, temperature, max_tokens, stream=False)
            else:
                raise ValueError(f"不支持的 LLM Provider: {self.provider}")

            # Metrics
            duration = time.time() - start
            LLM_DURATION.labels(provider=self.provider, model=self.ollama_model, endpoint="chat").observe(duration)
            LLM_REQUESTS.labels(provider=self.provider, model=self.ollama_model, endpoint="chat", status="success").inc()
            # 估算 token 数 (中文字符约1token，英文约4字符1token)
            estimated_tokens = len(result) // 2
            LLM_TOKENS_GENERATED.labels(provider=self.provider, model=self.ollama_model).inc(estimated_tokens)

            return result
        except Exception as e:
            status = "error"
            LLM_REQUESTS.labels(provider=self.provider, model=self.ollama_model, endpoint="chat", status="error").inc()
            raise

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """
        流式对话调用，逐字返回生成内容（SSE 格式）
        """
        start = time.time()
        total_chars = 0
        try:
            if self.provider == "ollama":
                async for chunk in self._chat_ollama_stream(messages, system_prompt, temperature, max_tokens):
                    total_chars += len(chunk)
                    yield chunk
            elif self.provider == "vllm":
                async for chunk in self._chat_vllm_stream(messages, system_prompt, temperature, max_tokens):
                    total_chars += len(chunk)
                    yield chunk
            else:
                raise ValueError(f"不支持的 LLM Provider: {self.provider}")

            # Metrics (流式在结束时记录)
            duration = time.time() - start
            LLM_DURATION.labels(provider=self.provider, model=self.ollama_model, endpoint="chat_stream").observe(duration)
            LLM_REQUESTS.labels(provider=self.provider, model=self.ollama_model, endpoint="chat_stream", status="success").inc()
            estimated_tokens = total_chars // 2
            LLM_TOKENS_GENERATED.labels(provider=self.provider, model=self.ollama_model).inc(estimated_tokens)
        except Exception:
            LLM_REQUESTS.labels(provider=self.provider, model=self.ollama_model, endpoint="chat_stream", status="error").inc()
            raise

    # ---------- Ollama 实现 ----------

    async def _chat_ollama(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> str:
        msgs = [m.dict() for m in messages]
        if system_prompt:
            # 在消息列表开头插入 system 消息
            msgs.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.ollama_model,
            "messages": msgs,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        resp = await self._client.post(self.ollama_chat_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    async def _chat_ollama_stream(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        msgs = [m.dict() for m in messages]
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.ollama_model,
            "messages": msgs,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with self._client.stream("POST", self.ollama_chat_url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    # ---------- vLLM 实现（预留） ----------

    async def _chat_vllm(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.vllm_api_key:
            headers["Authorization"] = f"Bearer {self.vllm_api_key}"

        msgs = [m.dict() for m in messages]
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.vllm_model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        resp = await self._client.post(self.vllm_api_url or "", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def _chat_vllm_stream(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        headers = {"Content-Type": "application/json"}
        if self.vllm_api_key:
            headers["Authorization"] = f"Bearer {self.vllm_api_key}"

        msgs = [m.dict() for m in messages]
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.vllm_model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with self._client.stream("POST", self.vllm_api_url or "", json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip().startswith("data: "):
                    json_str = line[len("data: "):]
                    if json_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(json_str)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    # ---------- 工具方法 ----------

    async def health_check(self) -> bool:
        """检查 LLM 服务是否可用"""
        try:
            if self.provider == "ollama":
                resp = await self._client.get(f"{self.settings.OLLAMA_HOST}/api/tags", timeout=10.0)
                resp.raise_for_status()
                models = resp.json().get("models", [])
                model_names = [m.get("name", m.get("model", "")) for m in models]
                return any(self.ollama_model in name for name in model_names)
            else:
                # vLLM 简单探测
                resp = await self._client.get(self.vllm_api_url.replace("/chat/completions", "/models"), timeout=10.0)
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"LLM 健康检查失败: {e}")
            return False

    async def close(self):
        await self._client.aclose()


# 全局单例（已迁移到 app.container，保留此函数兼容现有代码）
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    try:
        from app.container import container, ensure_registered
        ensure_registered()
        return container.resolve(LLMService)
    except Exception:
        pass
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
