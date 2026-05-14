"""
会话管理接口
- POST   /api/conversations              创建会话
- GET    /api/conversations              获取会话列表
- GET    /api/conversations/{id}         获取会话详情（含消息历史）
- PUT    /api/conversations/{id}         更新会话标题
- DELETE /api/conversations/{id}         删除会话
"""
import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_metadata_store
from app.models.schemas import (
    BaseResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationUpdateRequest,
)

router = APIRouter(tags=["Conversation"])


@router.post("/conversations", response_model=ConversationDetailResponse)
async def create_conversation(
    request: ConversationCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建新会话"""
    store = await get_metadata_store()
    conversation_id = uuid.uuid4().hex[:16]
    await store.create_conversation(
        conversation_id,
        title=request.title or "新会话",
        user_id=current_user["user_id"],
    )
    conv = await store.get_conversation(conversation_id, user_id=current_user["user_id"])
    return ConversationDetailResponse(
        data=ConversationDetailResponse.ConversationDetail(
            conversation_id=conv["conversation_id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            messages=[],
        )
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(current_user: dict = Depends(get_current_user)):
    """获取当前用户的会话列表"""
    store = await get_metadata_store()
    conversations = await store.list_conversations(user_id=current_user["user_id"])
    from app.models.schemas import ConversationInfo
    return ConversationListResponse(
        data=[
            ConversationInfo(
                conversation_id=c["conversation_id"],
                title=c["title"],
                created_at=c["created_at"],
                updated_at=c["updated_at"],
            )
            for c in conversations
        ]
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取会话详情，包含消息历史（只能访问自己的会话）"""
    store = await get_metadata_store()
    conv = await store.get_conversation(conversation_id, user_id=current_user["user_id"])
    if not conv:
        return BaseResponse(code=404, message="会话不存在", data=None)

    messages = await store.get_messages_by_conversation(conversation_id)
    return ConversationDetailResponse(
        data=ConversationDetailResponse.ConversationDetail(
            conversation_id=conv["conversation_id"],
            title=conv["title"],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
            messages=messages,
        )
    )


@router.put("/conversations/{conversation_id}", response_model=BaseResponse)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新会话标题（只能更新自己的会话）"""
    store = await get_metadata_store()
    # 先校验归属
    conv = await store.get_conversation(conversation_id, user_id=current_user["user_id"])
    if not conv:
        return BaseResponse(code=404, message="会话不存在", data=None)

    ok = await store.update_conversation_title(conversation_id, request.title)
    return BaseResponse(data={"conversation_id": conversation_id, "title": request.title})


@router.delete("/conversations/{conversation_id}", response_model=BaseResponse)
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除会话及其所有消息（只能删除自己的会话）"""
    store = await get_metadata_store()
    # 先校验归属
    conv = await store.get_conversation(conversation_id, user_id=current_user["user_id"])
    if not conv:
        return BaseResponse(code=404, message="会话不存在", data=None)

    ok = await store.delete_conversation(conversation_id)
    if not ok:
        return BaseResponse(code=404, message="会话不存在", data=None)
    return BaseResponse(data={"conversation_id": conversation_id})
