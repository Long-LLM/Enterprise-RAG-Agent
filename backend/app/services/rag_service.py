"""
RAG 问答编排服务
完整流程：
1. 问题理解与优化（Query Rewriting）
2. 混合检索（Hybrid Retrieval）
3. 重排序（Rerank）
4. Prompt 工程（带引用来源）
5. LLM 生成回答
6. 返回带来源引用的结果
"""
import time
from typing import AsyncIterator, Dict, List, Optional

from app.config import get_settings
from app.core.llm import ChatMessage, get_llm_service
from app.core.reranker import get_reranker_service
from app.core.retrieval import get_hybrid_retriever
from app.logger import get_logger, log_performance
from app.models.schemas import QueryRequest, SourceReference

logger = get_logger(__name__)
settings = get_settings()


class RAGService:
    """
    RAG 问答服务
    支持意图判断：区分知识库问答 vs 闲聊/问候/感谢
    """

    # ---------- 意图判断 ----------

    # 规则匹配：常见闲聊关键词（快速路径，不走 LLM 判断）
    CHITCHAT_KEYWORDS = {
        "你好", "您好", "嗨", "hello", "hi", "hey",
        "再见", "拜拜", "bye", "goodbye",
        "谢谢", "感谢", "thx", "thanks", "thank you",
        "你是谁", "你能做什么", "介绍一下自己", "你是谁啊",
        "早上好", "下午好", "晚上好", "晚安",
        "在吗", "在嘛", "有人吗", "hello?",
        "ok", "好的", "知道了", "明白", "收到",
    }

    INTENT_PROMPT = """判断用户问题的意图。只需回答一个JSON。

分类规则：
- "retrieve": 需要查询知识库才能回答的问题（如政策、流程、文档内容、事实性问题）
- "chat": 闲聊、问候、感谢、自我介绍请求、与知识库无关的通用对话

示例：
- "你好" -> {"intent": "chat", "reason": "问候语"}
- "公司的年假政策是什么？" -> {"intent": "retrieve", "reason": "需要查询公司政策文档"}
- "谢谢" -> {"intent": "chat", "reason": "感谢语"}
- "你是谁" -> {"intent": "chat", "reason": "询问助手身份"}
- "这个产品的价格是多少？" -> {"intent": "retrieve", "reason": "需要查询产品文档"}
- "帮我总结一下这段内容" -> {"intent": "retrieve", "reason": "需要基于已有文档总结"}

用户问题：{question}

请输出JSON（不要markdown代码块）：
{"intent": "chat 或 retrieve", "reason": "简要说明"}"""

    CHAT_SYSTEM_PROMPT = """你是一个友好、专业的企业助手。用户的问题不需要查询知识库，请直接自然地回答。

回答规则：
1. 友好、简洁、专业
2. 如果是问候，礼貌回应并简要说明自己是企业知识库助手
3. 如果是感谢，礼貌接受
4. 不要编造不存在的文档或信息
5. 如果用户询问你能做什么，简要说明可以基于企业知识库回答文档相关问题"""

    SYSTEM_PROMPT_TEMPLATE = """你是一个企业知识库助手，专门基于提供的参考文档回答用户问题。

## 回答规则：
1. 严格基于【参考文档】内容回答，不要编造信息
2. 如果参考文档不足以回答问题，请明确告知用户"根据现有资料无法回答"
3. 回答中需要引用来源时，使用 [^1], [^2] 等标记对应参考文档序号
4. 保持回答简洁、专业、结构化

## 参考文档：
{context}

请回答用户的问题。"""

    def __init__(self):
        self.llm = get_llm_service()
        self.retriever = get_hybrid_retriever()
        self.reranker = get_reranker_service()

    # ---------- 意图判断 ----------

    def _is_chitchat_by_rule(self, question: str) -> bool:
        """规则匹配：常见闲聊/问候/感谢语"""
        q = question.strip().lower()
        # 完全匹配关键词
        if q in self.CHITCHAT_KEYWORDS:
            return True
        # 长度极短（<=6 字）且不含问号，大概率是问候或简短回应
        if len(question.strip()) <= 6 and "?" not in question and "？" not in question:
            return True
        return False

    async def _detect_intent(self, question: str) -> tuple:
        """
        意图判断
        :return: (needs_retrieve: bool, reason: str)
        """
        # 1. 规则快速路径
        if self._is_chitchat_by_rule(question):
            logger.info(f"意图判断(规则): '{question}' -> 闲聊")
            return False, "规则命中：问候/感谢/闲聊"

        # 2. LLM 判断（轻量级，temperature=0）
        try:
            prompt = self.INTENT_PROMPT.format(question=question)
            resp = await self.llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.0,
                max_tokens=128,
                stream=False,
            )
            import json
            text = resp.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            data = json.loads(text)
            intent = data.get("intent", "retrieve")
            reason = data.get("reason", "")
            needs_retrieve = intent == "retrieve"
            logger.info(f"意图判断(LLM): '{question}' -> {'检索' if needs_retrieve else '闲聊'} ({reason})")
            return needs_retrieve, reason
        except Exception as e:
            logger.warning(f"意图判断(LLM)失败，默认走检索: {e}")
            return True, "意图判断失败，默认检索"

    # ---------- 闲聊直接回答 ----------

    async def _chat_direct(self, req: QueryRequest, history_messages: Optional[List[ChatMessage]] = None) -> dict:
        """不走检索，直接用通用助手回答"""
        start_time = time.time()
        messages = list(history_messages) if history_messages else []
        messages.append(ChatMessage(role="user", content=req.question))
        answer = await self.llm.chat(
            messages=messages,
            system_prompt=self.CHAT_SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=2048,
            stream=False,
        )
        return {
            "answer": answer.strip(),
            "sources": [],
            "model": settings.OLLAMA_LLM_MODEL if settings.LLM_PROVIDER == "ollama" else settings.VLLM_MODEL,
            "processing_time_ms": round((time.time() - start_time) * 1000, 2),
        }

    async def _chat_direct_stream(self, req: QueryRequest, history_messages: Optional[List[ChatMessage]] = None) -> AsyncIterator[str]:
        """不走检索，直接流式回答"""
        start_time = time.time()
        messages = list(history_messages) if history_messages else []
        messages.append(ChatMessage(role="user", content=req.question))

        import json
        # 空 sources
        meta = json.dumps({"type": "sources", "data": []}, ensure_ascii=False)
        yield f"data: {meta}\n\n"

        async for chunk in self.llm.chat_stream(
            messages=messages,
            system_prompt=self.CHAT_SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=2048,
        ):
            payload = json.dumps({"type": "token", "data": chunk}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        done_payload = json.dumps(
            {"type": "done", "processing_time_ms": round((time.time() - start_time) * 1000, 2)},
            ensure_ascii=False,
        )
        yield f"data: {done_payload}\n\n"

    # ---------- 主入口 ----------

    @log_performance(level=20, log_args=False)
    async def query(self, req: QueryRequest, history_messages: Optional[List[ChatMessage]] = None) -> dict:
        """
        非流式 RAG 查询（带意图判断）
        """
        # 0. 意图判断
        needs_retrieve, reason = await self._detect_intent(req.question)
        if not needs_retrieve:
            return await self._chat_direct(req, history_messages)

        # --- 以下走完整 RAG 流程 ---
        start_time = time.time()

        # 1. 问题改写
        rewritten_queries = await self._rewrite_query(req.question, history_messages)

        # 2. 多查询混合检索
        candidates = await self._multi_query_retrieve(
            queries=rewritten_queries,
            top_k_vector=settings.TOP_K_VECTOR,
            top_k_bm25=settings.TOP_K_BM25,
            filters=self._build_filter(req.filters),
        )

        # 3. 重排序
        if req.use_rerank and candidates:
            candidates = await self.reranker.rerank(
                query=req.question,
                candidates=candidates,
                top_k=settings.TOP_K_RERANK,
            )
        else:
            candidates = candidates[: req.top_k]

        # 4. 构造 Prompt
        context, sources = self._build_context(candidates)
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(context=context)

        # 5. LLM 生成
        messages = list(history_messages) if history_messages else []
        messages.append(ChatMessage(role="user", content=req.question))
        answer = await self.llm.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=2048,
            stream=False,
        )

        processing_time = (time.time() - start_time) * 1000

        return {
            "answer": answer.strip(),
            "sources": sources,
            "model": settings.OLLAMA_LLM_MODEL if settings.LLM_PROVIDER == "ollama" else settings.VLLM_MODEL,
            "processing_time_ms": round(processing_time, 2),
        }

    @log_performance(level=20, log_args=False)
    async def query_stream(self, req: QueryRequest, history_messages: Optional[List[ChatMessage]] = None) -> AsyncIterator[str]:
        """
        流式 RAG 查询（带意图判断）
        """
        # 0. 意图判断
        needs_retrieve, reason = await self._detect_intent(req.question)
        if not needs_retrieve:
            async for chunk in self._chat_direct_stream(req, history_messages):
                yield chunk
            return

        # --- 以下走完整 RAG 流程 ---
        start_time = time.time()

        # 1. 问题改写
        rewritten_queries = await self._rewrite_query(req.question, history_messages)

        # 2. 多查询混合检索
        candidates = await self._multi_query_retrieve(
            queries=rewritten_queries,
            top_k_vector=settings.TOP_K_VECTOR,
            top_k_bm25=settings.TOP_K_BM25,
            filters=self._build_filter(req.filters),
        )

        # 3. 重排序
        if req.use_rerank and candidates:
            candidates = await self.reranker.rerank(
                query=req.question,
                candidates=candidates,
                top_k=settings.TOP_K_RERANK,
            )
        else:
            candidates = candidates[: req.top_k]

        # 4. 构造 Prompt
        context, sources = self._build_context(candidates)
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(context=context)

        # 先返回 sources JSON
        import json
        meta = json.dumps({"type": "sources", "data": [s.model_dump() for s in sources]}, ensure_ascii=False)
        yield f"data: {meta}\n\n"

        # 5. 流式生成
        messages = list(history_messages) if history_messages else []
        messages.append(ChatMessage(role="user", content=req.question))
        async for chunk in self.llm.chat_stream(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=2048,
        ):
            payload = json.dumps({"type": "token", "data": chunk}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        done_payload = json.dumps(
            {"type": "done", "processing_time_ms": round((time.time() - start_time) * 1000, 2)},
            ensure_ascii=False,
        )
        yield f"data: {done_payload}\n\n"

    REWRITE_PROMPT = """你是一位专业的查询改写助手。请根据用户的历史对话和当前问题，生成适合向量检索的改写问句。

任务要求：
1. 补全多轮对话中省略的上下文信息（如指代、省略主语等）
2. 消除口语化表达，转化为正式的检索问句
3. 保持用户原始意图，不改变原意
4. 不添加原文中没有的信息
5. 不过度扩写，避免语义偏移
6. 专业名词保持原样，严禁替换
7. 生成2-3条不同角度的候选检索问句，提高召回率
8. 如问题复杂，拆解为子问题

输出格式（必须是合法JSON，不要markdown代码块）：
{{"queries": ["改写问句1", "改写问句2", "改写问句3"], "reasoning": "简要说明改写思路"}}

历史对话：
{history}

当前问题：{query}

请输出JSON："""

    async def _rewrite_query(self, query: str, history_messages: Optional[List[ChatMessage]] = None) -> List[str]:
        """
        查询重写/优化
        使用 LLM 对模糊问题进行澄清和扩展，返回多条候选查询
        """
        # 构建历史对话文本
        history_text = ""
        if history_messages:
            for msg in history_messages[-6:]:  # 只取最近6轮
                role = "用户" if msg.role == "user" else "助手"
                history_text += f"{role}：{msg.content}\n"

        prompt = self.REWRITE_PROMPT.format(
            history=history_text or "无",
            query=query,
        )

        try:
            resp = await self.llm.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=0.1,
                max_tokens=1024,
                stream=False,
            )
            import json
            # 尝试提取JSON
            text = resp.strip()
            # 去除可能的markdown代码块
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            queries = data.get("queries", [])
            if not queries:
                return [query.strip()]
            # 去重并保留原问题
            seen = set()
            result = []
            for q in queries:
                q = q.strip()
                if q and q not in seen:
                    seen.add(q)
                    result.append(q)
            # 始终包含原始问题作为保底
            original = query.strip()
            if original not in seen:
                result.insert(0, original)
            logger.info(f"查询改写: '{query}' -> {result}")
            return result[:4]  # 最多4条
        except Exception as e:
            logger.warning(f"查询改写失败，使用原查询: {e}")
            return [query.strip()]

    async def _multi_query_retrieve(
        self,
        queries: List[str],
        top_k_vector: int,
        top_k_bm25: int,
        filters: Optional[str],
    ) -> List[Dict]:
        """
        多查询检索：对每个改写查询分别检索，合并去重后按分数排序
        """
        if len(queries) == 1:
            return await self.retriever.retrieve(
                query=queries[0],
                top_k_vector=top_k_vector,
                top_k_bm25=top_k_bm25,
                filters=filters,
            )

        all_results: Dict[str, Dict] = {}
        for q in queries:
            try:
                results = await self.retriever.retrieve(
                    query=q,
                    top_k_vector=top_k_vector,
                    top_k_bm25=top_k_bm25,
                    filters=filters,
                )
                for r in results:
                    chunk_id = r.get("chunk_id")
                    if not chunk_id:
                        continue
                    if chunk_id not in all_results:
                        all_results[chunk_id] = r.copy()
                        all_results[chunk_id]["_score_sum"] = r.get("rrf_score", 0.0)
                        all_results[chunk_id]["_hit_count"] = 1
                    else:
                        # 累加分数，提高被多个查询命中的chunk的权重
                        all_results[chunk_id]["_score_sum"] += r.get("rrf_score", 0.0)
                        all_results[chunk_id]["_hit_count"] += 1
            except Exception as e:
                logger.warning(f"多查询检索中查询 '{q}' 失败: {e}")

        # 按综合分数排序：命中次数 * 平均分数
        sorted_items = sorted(
            all_results.values(),
            key=lambda x: x["_hit_count"] * x["_score_sum"],
            reverse=True,
        )
        # 清理内部字段
        for item in sorted_items:
            item.pop("_score_sum", None)
            item.pop("_hit_count", None)

        return sorted_items

    def _build_filter(self, filters: Optional[dict]) -> Optional[str]:
        """
        构建 Milvus 过滤表达式
        filters 示例: {"doc_id": "xxx"}
        """
        if not filters:
            return None
        exprs = []
        for k, v in filters.items():
            if isinstance(v, str):
                exprs.append(f'{k} == "{v}"')
            elif isinstance(v, (int, float)):
                exprs.append(f"{k} == {v}")
            elif isinstance(v, list):
                if all(isinstance(x, str) for x in v):
                    vals = ",".join([f'"{x}"' for x in v])
                    exprs.append(f"{k} in [{vals}]")
        return " and ".join(exprs) if exprs else None

    def _build_context(self, candidates: List[dict]) -> tuple:
        """
        构建 LLM 上下文和来源引用列表
        :return: (context_string, List[SourceReference])
        """
        context_parts = []
        sources = []

        for i, cand in enumerate(candidates, start=1):
            content = cand.get("content", "").strip()
            if not content:
                continue

            # 父子分块：优先使用父块内容作为上下文
            context_content = cand.get("parent_content", "") or content
            context_parts.append(f"[{i}] {context_content}")
            sources.append(
                SourceReference(
                    doc_id=cand.get("doc_id", ""),
                    title=cand.get("title") or cand.get("filename"),
                    filename=cand.get("filename"),
                    content=content[:500],  # 截断用于展示
                    score=round(cand.get("rerank_score", cand.get("rrf_score", 0.0)), 4),
                    page_number=cand.get("page_number") if cand.get("page_number") else None,
                    chunk_index=cand.get("chunk_index"),
                    parent_content=cand.get("parent_content"),
                    chunk_type=cand.get("chunk_type", "normal"),
                )
            )

        context = "\n\n".join(context_parts)
        return context, sources


# 全局单例（已迁移到 app.container，保留此函数兼容现有代码）
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    try:
        from app.container import container, ensure_registered
        ensure_registered()
        return container.resolve(RAGService)
    except Exception as e:
        import traceback
        from app.logger import get_logger
        logger = get_logger(__name__)
        logger.error(f"Container resolve RAGService failed: {e}")
        traceback.print_exc()
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
