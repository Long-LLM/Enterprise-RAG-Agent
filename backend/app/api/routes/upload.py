"""
文档上传与处理接口
- POST /api/upload       - 同步上传（保持兼容）
- POST /api/upload/async - 异步上传（推荐，大文件用）
- GET  /api/tasks/{task_id} - 查询异步任务状态
"""
import json
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_current_user, get_document_service, get_metadata_store
from app.core.celery_app import celery_app
from app.core.tasks import process_document
from app.logger import get_logger
from app.models.schemas import (
    AsyncTaskStatusResponse,
    AsyncUploadResponse,
    BaseResponse,
    DocumentUploadResponse,
)

router = APIRouter(tags=["Documents"])
logger = get_logger(__name__)


def _check_upload_permission(current_user: dict, department: Optional[str]) -> tuple:
    """
    检查上传权限
    返回: (ok: bool, department: str|None, error_response: BaseResponse|None)
    """
    role = current_user.get("role", "user")
    user_dept = current_user.get("department")

    if role == "user":
        return False, None, BaseResponse(code=403, message="普通用户无权上传文档")

    if role == "staff":
        if not user_dept:
            return False, None, BaseResponse(code=403, message="员工未分配部门，请联系管理员")
        if department and department != user_dept:
            return False, None, BaseResponse(code=403, message=f"只能上传到自己所属部门: {user_dept}")
        department = user_dept

    return True, department, None


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="上传的文档文件 (PDF/DOCX/TXT/MD/HTML/PPTX)"),
    title: Optional[str] = Form(default=None, description="文档标题（可选，默认使用文件名）"),
    chunk_strategy: str = Form(default="auto", description="分块策略: auto/fixed_size/recursive/semantic/structured/parent_child/llm_smart"),
    strategy_params: Optional[str] = Form(default=None, description="策略参数 JSON 字符串"),
    department: Optional[str] = Form(default=None, description="存入的部门/数据库"),
    current_user: dict = Depends(get_current_user),
):
    """
    同步上传文档并自动处理入库。
    适合小文件（< 10MB），大文件请使用 /upload/async
    """
    ok, department, error = _check_upload_permission(current_user, department)
    if not ok:
        return error

    if not file.filename:
        return BaseResponse(code=400, message="文件名不能为空")

    content = await file.read()
    if not content:
        return BaseResponse(code=400, message="文件内容为空")

    params = None
    if strategy_params:
        try:
            params = json.loads(strategy_params)
        except json.JSONDecodeError:
            return BaseResponse(code=400, message="策略参数 JSON 格式错误")

    service = get_document_service()
    result = await service.process_upload(
        file_bytes=content,
        filename=file.filename,
        title=title,
        chunk_strategy=chunk_strategy,
        strategy_params=params,
        department=department,
    )

    # 自动设为公共查询权限
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


@router.post("/upload/async", response_model=AsyncUploadResponse)
async def upload_document_async(
    file: UploadFile = File(..., description="上传的文档文件"),
    title: Optional[str] = Form(default=None),
    chunk_strategy: str = Form(default="auto"),
    strategy_params: Optional[str] = Form(default=None),
    department: Optional[str] = Form(default=None),
    current_user: dict = Depends(get_current_user),
):
    """
    异步上传文档。
    文件保存后交由 Celery Worker 后台处理，立即返回 task_id 用于轮询进度。
    适合大文件或批量处理场景。
    """
    ok, department, error = _check_upload_permission(current_user, department)
    if not ok:
        return error

    if not file.filename:
        return BaseResponse(code=400, message="文件名不能为空")

    content = await file.read()
    if not content:
        return BaseResponse(code=400, message="文件内容为空")

    params = None
    if strategy_params:
        try:
            params = json.loads(strategy_params)
        except json.JSONDecodeError:
            return BaseResponse(code=400, message="策略参数 JSON 格式错误")

    # 保存到临时文件
    upload_dir = Path("./uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    temp_path = upload_dir / f"{uuid.uuid4().hex}_{file.filename}"
    temp_path.write_bytes(content)

    # 提交 Celery 任务
    doc_id = str(uuid.uuid4())
    task = process_document.delay(
        file_path=str(temp_path),
        filename=file.filename,
        title=title,
        chunk_strategy=chunk_strategy,
        strategy_params=params,
        department=department,
    )

    logger.info(f"[Async Upload] 任务已提交: task_id={task.id}, doc_id={doc_id}, file={file.filename}")

    return AsyncUploadResponse(
        data=AsyncUploadResponse.UploadTaskData(
            task_id=task.id,
            doc_id=doc_id,
            filename=file.filename,
            status="PENDING",
        )
    )


@router.get("/tasks/{task_id}", response_model=AsyncTaskStatusResponse)
async def get_task_status(
    task_id: str,
    _: dict = Depends(get_current_user),
):
    """
    查询异步任务状态
    """
    task_result = AsyncResult(task_id, app=celery_app)

    response_data = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "progress": None,
        "stage": None,
        "message": None,
        "doc_id": None,
    }

    if task_result.ready():
        if task_result.successful():
            result = task_result.result
            response_data["result"] = result
            response_data["doc_id"] = result.get("doc_id") if isinstance(result, dict) else None
            response_data["message"] = "处理完成"
        else:
            response_data["message"] = str(task_result.result)
    elif task_result.state == "PROGRESS":
        meta = task_result.info or {}
        response_data["progress"] = meta.get("progress")
        response_data["stage"] = meta.get("stage")
        response_data["message"] = meta.get("message")
        response_data["doc_id"] = meta.get("doc_id")
    else:
        response_data["message"] = "等待处理中..."

    return AsyncTaskStatusResponse(data=AsyncTaskStatusResponse.TaskData(**response_data))
