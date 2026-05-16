"""
Pydantic 请求/响应模型定义
"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ========================== 通用 ==========================

class BaseResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None


# ========================== 文档上传 ==========================

class DocumentUploadResponse(BaseResponse):
    class UploadData(BaseModel):
        doc_id: str
        filename: str
        chunk_count: int
        status: str

    data: UploadData


# ========================== 文档管理 ==========================

class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    title: Optional[str] = None
    chunk_count: int = 0
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    department: Optional[str] = None
    created_at: Optional[datetime] = None
    status: str = "active"  # active | processing | failed


class DocumentListResponse(BaseResponse):
    data: List[DocumentInfo]


class DocumentDeleteResponse(BaseResponse):
    class DeleteData(BaseModel):
        deleted_count: int

    data: DeleteData


# ========================== 问答查询 ==========================

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="用户问题")
    top_k: int = Field(default=5, ge=1, le=20, description="返回结果数量")
    use_rerank: bool = Field(default=True, description="是否启用重排序")
    stream: bool = Field(default=False, description="是否流式输出")
    conversation_id: Optional[str] = Field(default=None, description="会话ID，用于多轮对话")
    filters: Optional[dict] = Field(default=None, description="附加过滤条件，如 doc_id 等")


class SourceReference(BaseModel):
    doc_id: str
    title: Optional[str] = None
    filename: Optional[str] = None
    content: str
    score: float
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    parent_content: Optional[str] = None
    chunk_type: Optional[str] = None


class QueryResponse(BaseResponse):
    class AnswerData(BaseModel):
        answer: str
        sources: List[SourceReference]
        model: str
        processing_time_ms: Optional[float] = None

    data: AnswerData


# ========================== 检索测试（调试用） ==========================

class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    use_rerank: bool = Field(default=True)


class RetrieveResult(BaseModel):
    doc_id: str
    content: str
    score: float
    rank_type: str  # "vector" | "bm25" | "rerank"


class RetrieveResponse(BaseResponse):
    data: List[RetrieveResult]


# ========================== 分块预览 ==========================

class ChunkPreviewItem(BaseModel):
    index: int
    content: str
    char_count: int
    section_title: Optional[str] = None
    heading_level: Optional[int] = None
    chunk_type: str = "normal"
    parent_id: Optional[str] = None
    metadata: Optional[dict] = None


class ChunkPreviewStats(BaseModel):
    avg_length: float
    max_length: int
    min_length: int
    total_chunks: int
    total_chars: int
    preview_truncated: bool = False


class ChunkPreviewResponse(BaseResponse):
    class PreviewData(BaseModel):
        strategy: str
        total_chars: int
        chunk_count: int
        chunks: List[ChunkPreviewItem]
        stats: ChunkPreviewStats

    data: PreviewData


# ========================== 会话管理 ==========================

class ConversationInfo(BaseModel):
    conversation_id: str
    title: str
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field(default="新会话", description="会话标题")


class ConversationUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256, description="会话标题")


class ConversationListResponse(BaseResponse):
    data: List[ConversationInfo]


class ConversationDetailResponse(BaseResponse):
    class ConversationDetail(BaseModel):
        conversation_id: str
        title: str
        created_at: Optional[int] = None
        updated_at: Optional[int] = None
        messages: List[dict] = []

    data: ConversationDetail


class MessageInfo(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    sources: List[dict] = []
    model: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: Optional[int] = None


# ========================== 用户鉴权 ==========================

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=64, description="密码")


class UserLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class UserInfo(BaseModel):
    user_id: str
    username: str
    role: str  # admin | staff | user
    department: Optional[str] = None
    created_at: Optional[int] = None


class TokenResponse(BaseResponse):
    class TokenData(BaseModel):
        access_token: str
        token_type: str = "bearer"
        user: UserInfo

    data: TokenData


class UserListResponse(BaseResponse):
    data: List[UserInfo]


# ========================== 权限管理 ==========================

class PermissionGrantRequest(BaseModel):
    user_id: str = Field(..., description="目标用户ID")
    doc_id: str = Field(..., description="文档ID")


class PermissionInfo(BaseModel):
    user_id: str
    doc_id: str
    granted_by: Optional[str] = None
    created_at: Optional[int] = None


class PermissionListResponse(BaseResponse):
    data: List[PermissionInfo]


class MyPermissionDocInfo(BaseModel):
    doc_id: str
    filename: str
    title: Optional[str] = None


class MyPermissionListResponse(BaseResponse):
    data: List[MyPermissionDocInfo]


# ========================== 异步任务 ==========================

class AsyncTaskStatusResponse(BaseResponse):
    class TaskData(BaseModel):
        task_id: str
        status: str  # PENDING / STARTED / PROGRESS / SUCCESS / FAILURE / RETRY
        result: Optional[dict] = None
        progress: Optional[int] = None
        stage: Optional[str] = None
        message: Optional[str] = None
        doc_id: Optional[str] = None

    data: TaskData


class AsyncUploadResponse(BaseResponse):
    class UploadTaskData(BaseModel):
        task_id: str
        doc_id: str
        filename: str
        status: str = "PENDING"

    data: UploadTaskData


# ========================== 系统健康 ==========================

class HealthCheckResponse(BaseResponse):
    class HealthData(BaseModel):
        status: str
        milvus_connected: bool
        ollama_connected: bool
        llm_provider: str
        version: str = "0.1.0"

    data: HealthData
