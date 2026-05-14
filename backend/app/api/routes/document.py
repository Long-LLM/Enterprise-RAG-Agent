"""
文档管理接口
- GET  /api/documents      列出所有文档
- GET  /api/documents/{id} 查看文档详情
- DELETE /api/documents/{id} 删除文档
- POST /api/documents/rebuild-bm25 重建 BM25 索引
"""
from typing import List

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_document_service, get_metadata_store
from app.models.schemas import BaseResponse, DocumentDeleteResponse, DocumentInfo, DocumentListResponse

router = APIRouter(tags=["Documents"])


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(current_user: dict = Depends(get_current_user)):
    """列出知识库中的文档（按角色隔离）"""
    service = get_document_service()
    docs = await service.list_documents()
    store = await get_metadata_store()
    role = current_user.get("role", "user")

    # 管理员返回全部
    if role == "admin":
        return DocumentListResponse(data=docs)

    # 员工：自己部门的 + 公共的
    if role == "staff":
        user_dept = current_user.get("department")
        public_ids = set(await store.get_public_doc_permissions())
        filtered = []
        for d in docs:
            if d.doc_id in public_ids or d.get("department") == user_dept:
                filtered.append(d)
        return DocumentListResponse(data=filtered)

    # 普通用户：只能看到公共文档
    public_ids = set(await store.get_public_doc_permissions())
    filtered = [d for d in docs if d.doc_id in public_ids]
    return DocumentListResponse(data=filtered)


@router.get("/documents/{doc_id}", response_model=BaseResponse)
async def get_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """获取文档详情及其分块列表"""
    role = current_user.get("role", "user")
    store = await get_metadata_store()

    if role != "admin":
        doc = await store.get_document(doc_id)
        if not doc:
            return BaseResponse(code=404, message="文档不存在", data=None)

        # 检查是否有权限访问
        is_public = doc_id in set(await store.get_public_doc_permissions())
        if role == "staff":
            if not is_public and doc.get("department") != current_user.get("department"):
                return BaseResponse(code=403, message="无权访问该文档", data=None)
        else:  # user
            if not is_public:
                return BaseResponse(code=403, message="无权访问该文档", data=None)

    service = get_document_service()
    chunks = await service.get_document_chunks(doc_id)
    return BaseResponse(
        data={
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }
    )


@router.delete("/documents/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(doc_id: str, current_user: dict = Depends(get_current_user)):
    """删除文档及其所有向量数据"""
    role = current_user.get("role", "user")
    store = await get_metadata_store()

    if role == "admin":
        service = get_document_service()
        deleted = await service.delete_document(doc_id)
        return DocumentDeleteResponse(
            data=DocumentDeleteResponse.DeleteData(deleted_count=deleted)
        )

    if role == "staff":
        doc = await store.get_document(doc_id)
        if doc and doc.get("department") == current_user.get("department"):
            service = get_document_service()
            deleted = await service.delete_document(doc_id)
            return DocumentDeleteResponse(
                data=DocumentDeleteResponse.DeleteData(deleted_count=deleted)
            )
        return DocumentDeleteResponse(code=403, message="无权删除该文档", data=None)

    return DocumentDeleteResponse(code=403, message="无权删除文档", data=None)


@router.post("/documents/rebuild-bm25", response_model=BaseResponse)
async def rebuild_bm25(current_user: dict = Depends(get_current_user)):
    """全量重建 BM25 索引（管理维护用）"""
    if current_user.get("role") != "admin":
        return BaseResponse(code=403, message="无权操作", data=None)

    service = get_document_service()
    await service.rebuild_bm25_index()
    return BaseResponse(message="BM25 索引重建完成")
