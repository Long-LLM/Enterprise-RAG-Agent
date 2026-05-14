"""
文档上传与处理接口
POST /api/upload - 上传文件并自动入库
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_current_user, get_document_service, get_metadata_store
from app.models.schemas import BaseResponse, DocumentUploadResponse

router = APIRouter(tags=["Documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="上传的文档文件 (PDF/DOCX/TXT/MD/HTML/PPTX)"),
    title: Optional[str] = Form(default=None, description="文档标题（可选，默认使用文件名）"),
    chunk_strategy: str = Form(default="auto", description="分块策略: auto/fixed_size/recursive/semantic/structured/parent_child/llm_smart"),
    strategy_params: Optional[str] = Form(default=None, description="策略参数 JSON 字符串"),
    department: Optional[str] = Form(default=None, description="存入的部门/数据库（管理员可选，员工默认为自己部门）"),
    current_user: dict = Depends(get_current_user),
):
    """
    上传文档并自动处理：
    1. 保存文件到本地
    2. 解析文档内容
    3. 智能分块
    4. Embedding 向量化
    5. 存入 Milvus 向量库
    6. 更新 BM25 索引
    7. 自动给当前用户添加该文档权限
    """
    role = current_user.get("role", "user")
    user_dept = current_user.get("department")

    # 权限检查
    if role == "user":
        return BaseResponse(code=403, message="普通用户无权上传文档")

    if role == "staff":
        if not user_dept:
            return BaseResponse(code=403, message="员工未分配部门，请联系管理员")
        # 员工只能上传到自己部门
        if department and department != user_dept:
            return BaseResponse(code=403, message=f"只能上传到自己所属部门: {user_dept}")
        department = user_dept

    # 管理员可以选择部门，默认不指定
    if not file.filename:
        return BaseResponse(code=400, message="文件名不能为空")

    # 读取文件内容
    content = await file.read()
    if not content:
        return BaseResponse(code=400, message="文件内容为空")

    # 解析策略参数
    params = None
    if strategy_params:
        try:
            params = json.loads(strategy_params)
        except json.JSONDecodeError:
            return BaseResponse(code=400, message="策略参数 JSON 格式错误")

    # 调用服务层处理
    service = get_document_service()
    result = await service.process_upload(
        file_bytes=content,
        filename=file.filename,
        title=title,
        chunk_strategy=chunk_strategy,
        strategy_params=params,
        department=department,
    )

    # 自动设为公共查询权限（所有用户可查询）
    store = await get_metadata_store()
    await store.grant_public_doc_permission(
        doc_id=result["doc_id"],
        granted_by=current_user["user_id"],
    )

    return DocumentUploadResponse(
        data=DocumentUploadResponse.UploadData(
            doc_id=result["doc_id"],
            filename=result["filename"],
            chunk_count=result["chunk_count"],
            status=result["status"],
        )
    )
