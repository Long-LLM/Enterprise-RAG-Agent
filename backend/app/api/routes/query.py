"""
智能问答接口 (RAG Query)
- POST /api/query       非流式问答
- POST /api/query/stream 流式问答 (SSE)
- POST /api/retrieve    检索调试（仅返回检索结果，不调用 LLM）
"""
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, get_metadata_store, get_rag_service
from app.config import get_settings
from app.core.llm import ChatMessage
from app.core.retrieval import get_hybrid_retriever
from app.models.schemas import (
    BaseResponse,
    QueryRequest,
    QueryResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrieveResult,
)

router = APIRouter(tags=["Query"])

settings = get_settings()


def _build_history_messages(raw_messages: list) -> list:
    """将数据库消息记录转换为 ChatMessage 列表"""
    history = []
    for msg in raw_messages:
        if msg["role"] in ("user", "assistant"):
            history.append(ChatMessage(role=msg["role"], content=msg["content"]))
    return history


async def _inject_doc_permission_filter(request: QueryRequest, current_user: dict) -> None:
    """根据当前用户权限自动注入 doc_id filter
    权限模型：
    - admin: 查询所有
    - staff: 查询公共文档 + 自己部门的文档
    - user: 查询公共文档
    """
    role = current_user.get("role", "user")
    if role == "admin":
        return  # 管理员无需过滤

    store = await get_metadata_store()

    # 获取公共文档ID
    public_doc_ids = set(await store.get_public_doc_permissions())

    # 员工额外获取自己部门的文档
    if role == "staff":
        user_dept = current_user.get("department")
        if user_dept:
            dept_docs = await store.list_documents_by_department(user_dept)
            dept_doc_ids = {d["doc_id"] for d in dept_docs}
            public_doc_ids = public_doc_ids | dept_doc_ids

    allowed_doc_ids = list(public_doc_ids)

    if not allowed_doc_ids:
        request.filters = request.filters or {}
        request.filters["doc_id"] = ["__NO_PERMISSION__"]
        return

    request.filters = request.filters or {}
    existing = request.filters.get("doc_id")
    if existing:
        if isinstance(existing, str):
            existing = [existing]
        if isinstance(existing, list):
            intersect = [d for d in existing if d in allowed_doc_ids]
            request.filters["doc_id"] = intersect if intersect else ["__NO_PERMISSION__"]
    else:
        request.filters["doc_id"] = allowed_doc_ids


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, current_user: dict = Depends(get_current_user)):
    """
    非流式智能问答
    返回完整回答和引用来源
    """
    store = await get_metadata_store()
    service = get_rag_service()

    # 0. 注入文档权限过滤
    await _inject_doc_permission_filter(request, current_user)

    # 1. 处理会话：若未提供 conversation_id 则自动创建
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = uuid.uuid4().hex[:16]
        await store.create_conversation(conversation_id, title=request.question[:30] or "新会话", user_id=current_user["user_id"])
    else:
        conv = await store.get_conversation(conversation_id, user_id=current_user["user_id"])
        if not conv:
            return BaseResponse(code=404, message="会话不存在", data=None)

    # 2. 获取历史消息（最近 10 条 = 5 轮）
    raw_messages = await store.get_messages_by_conversation(conversation_id)
    history_messages = _build_history_messages(raw_messages[-10:])

    # 3. 执行 RAG 查询（带历史上下文）
    result = await service.query(request, history_messages=history_messages)

    # 4. 保存用户消息
    user_msg_id = uuid.uuid4().hex[:16]
    await store.save_message(
        message_id=user_msg_id,
        conversation_id=conversation_id,
        role="user",
        content=request.question,
    )

    # 5. 保存助手消息
    assistant_msg_id = uuid.uuid4().hex[:16]
    await store.save_message(
        message_id=assistant_msg_id,
        conversation_id=conversation_id,
        role="assistant",
        content=result["answer"],
        sources=[s.model_dump() for s in result["sources"]],
        model=result["model"],
        processing_time_ms=result["processing_time_ms"],
    )

    # 6. 更新会话时间
    await store.update_conversation_time(conversation_id)

    return QueryResponse(
        data=QueryResponse.AnswerData(
            answer=result["answer"],
            sources=result["sources"],
            model=result["model"],
            processing_time_ms=result["processing_time_ms"],
        )
    )


async def _save_stream_message(
    assistant_msg_id: str,
    conversation_id: str,
    save_state: dict,
) -> None:
    """后台任务：保存流式生成的助手消息（即使客户端断开也会执行）"""
    try:
        store = await get_metadata_store()
        model = settings.OLLAMA_LLM_MODEL if settings.LLM_PROVIDER == "ollama" else settings.VLLM_MODEL
        await store.save_message(
            message_id=assistant_msg_id,
            conversation_id=conversation_id,
            role="assistant",
            content=save_state.get("content", ""),
            sources=save_state.get("sources", []),
            model=model,
            processing_time_ms=save_state.get("time", 0),
        )
        await store.update_conversation_time(conversation_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"后台保存流式消息失败: {e}")


@router.post("/query/stream")
async def query_stream(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """
    流式智能问答 (SSE)
    前端使用 EventSource 接收
    使用 BackgroundTasks 确保客户端断开时消息仍被保存
    """
    store = await get_metadata_store()
    service = get_rag_service()

    # 0. 注入文档权限过滤
    await _inject_doc_permission_filter(request, current_user)

    # 1. 处理会话
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = uuid.uuid4().hex[:16]
        await store.create_conversation(conversation_id, title=request.question[:30] or "新会话", user_id=current_user["user_id"])
    else:
        conv = await store.get_conversation(conversation_id, user_id=current_user["user_id"])
        if not conv:
            return BaseResponse(code=404, message="会话不存在", data=None)

    # 2. 获取历史消息
    raw_messages = await store.get_messages_by_conversation(conversation_id)
    history_messages = _build_history_messages(raw_messages[-10:])

    # 3. 预先保存用户消息
    user_msg_id = uuid.uuid4().hex[:16]
    await store.save_message(
        message_id=user_msg_id,
        conversation_id=conversation_id,
        role="user",
        content=request.question,
    )

    assistant_msg_id = uuid.uuid4().hex[:16]

    # 共享状态：event_generator 实时写入，background_tasks 最终读取保存
    save_state = {"content": "", "sources": [], "time": 0}

    async def event_generator():
        async for chunk in service.query_stream(request, history_messages=history_messages):
            # 解析 chunk 提取内容用于后台保存
            if chunk.startswith("data: "):
                try:
                    payload = json.loads(chunk[6:].strip())
                    if payload.get("type") == "token":
                        save_state["content"] += payload.get("data", "")
                    elif payload.get("type") == "sources":
                        save_state["sources"] = payload.get("data", [])
                    elif payload.get("type") == "done":
                        save_state["time"] = payload.get("processing_time_ms", 0)
                except Exception:
                    pass
            yield chunk

    # 注册后台保存任务（响应结束后执行，不受客户端断开影响）
    background_tasks.add_task(
        _save_stream_message,
        assistant_msg_id,
        conversation_id,
        save_state,
    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_debug(request: RetrieveRequest, current_user: dict = Depends(get_current_user)):
    """
    检索调试接口
    仅执行混合检索，不调用 LLM，用于调试检索质量
    """
    # 注入文档权限过滤（与 query/query_stream 保持一致）
    filters = None
    role = current_user.get("role", "user")
    if role != "admin":
        store = await get_metadata_store()
        public_doc_ids = set(await store.get_public_doc_permissions())

        if role == "staff":
            user_dept = current_user.get("department")
            if user_dept:
                dept_docs = await store.list_documents_by_department(user_dept)
                public_doc_ids = public_doc_ids | {d["doc_id"] for d in dept_docs}

        allowed_doc_ids = list(public_doc_ids)
        if allowed_doc_ids:
            vals = ",".join([f'"{d}"' for d in allowed_doc_ids])
            filters = f'doc_id in [{vals}]'
        else:
            filters = 'doc_id == "__NO_PERMISSION__"'

    retriever = get_hybrid_retriever()
    from app.core.embedding import get_embedding_service

    embed = get_embedding_service()

    # 向量检索（带权限过滤）
    query_embed = await embed.embed_query(request.query)
    vector_results = retriever.milvus.search_by_vector(
        embedding=query_embed,
        top_k=request.top_k,
        filters=filters,
    )

    # BM25 检索（后过滤权限）
    bm25_results = retriever.bm25.search(request.query, top_k=request.top_k * 3) if retriever._bm25_built else []
    if filters and bm25_results:
        # 提取允许的 doc_id 列表进行后过滤
        allowed_doc_ids = set()
        if 'doc_id in [' in filters:
            import re
            matches = re.findall(r'"([^"]+)"', filters)
            allowed_doc_ids = set(matches)
        bm25_results = [r for r in bm25_results if r.get("doc_id") in allowed_doc_ids]
        bm25_results = bm25_results[:request.top_k]

    # 合并去重展示
    seen = set()
    results = []
    for r in vector_results:
        cid = r.get("chunk_id")
        if cid and cid not in seen:
            seen.add(cid)
            results.append(
                RetrieveResult(
                    doc_id=r.get("doc_id", ""),
                    content=r.get("content", "")[:300],
                    score=round(r.get("distance", 0.0), 4),
                    rank_type="vector",
                )
            )
    for r in bm25_results:
        cid = r.get("chunk_id")
        if cid and cid not in seen:
            seen.add(cid)
            results.append(
                RetrieveResult(
                    doc_id=r.get("doc_id", ""),
                    content=r.get("content", "")[:300],
                    score=round(r.get("bm25_score", 0.0), 4),
                    rank_type="bm25",
                )
            )

    # 按分数排序
    results.sort(key=lambda x: x.score, reverse=True)
    return RetrieveResponse(data=results[: request.top_k])
