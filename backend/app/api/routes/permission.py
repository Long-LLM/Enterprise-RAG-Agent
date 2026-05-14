"""
权限管理接口（仅管理员可访问）
- GET    /api/users              列出所有用户
- GET    /api/permissions/me     当前用户有权限的文档
- POST   /api/permissions        分配权限（admin）
- DELETE /api/permissions        取消权限（admin）
- GET    /api/permissions/{user_id} 查看某用户权限（admin）
- POST   /api/users/{user_id}/department 设置用户部门（admin）
- GET    /api/departments        列出所有部门
- POST   /api/documents/{doc_id}/public  设置文档为公共查询（admin）
- DELETE /api/documents/{doc_id}/public  撤销文档公共查询（admin）
- GET    /api/documents/public   获取所有公共文档
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_metadata_store
from app.core.security import get_current_user, require_admin
from app.models.schemas import (
    BaseResponse,
    MyPermissionDocInfo,
    MyPermissionListResponse,
    PermissionGrantRequest,
    PermissionListResponse,
    UserListResponse,
)

router = APIRouter(tags=["Permission"])


@router.get("/users", response_model=UserListResponse)
async def list_users(_: dict = Depends(require_admin)):
    """列出所有用户（管理员）"""
    store = await get_metadata_store()
    users = await store.list_users()
    from app.models.schemas import UserInfo
    return UserListResponse(
        data=[
            UserInfo(
                user_id=u["user_id"],
                username=u["username"],
                role=u["role"],
                department=u.get("department"),
                created_at=u["created_at"],
            )
            for u in users
        ]
    )


@router.get("/permissions/me", response_model=MyPermissionListResponse)
async def list_my_permissions(current_user: dict = Depends(get_current_user)):
    """获取当前用户有权限的文档列表（公共文档 + 自己部门的文档）"""
    store = await get_metadata_store()
    role = current_user.get("role", "user")

    doc_ids = set(await store.get_public_doc_permissions())

    if role == "staff":
        user_dept = current_user.get("department")
        if user_dept:
            dept_docs = await store.list_documents_by_department(user_dept)
            doc_ids.update(d["doc_id"] for d in dept_docs)

    if not doc_ids:
        return MyPermissionListResponse(data=[])

    docs = []
    for doc_id in doc_ids:
        doc = await store.get_document(doc_id)
        if doc:
            docs.append(
                MyPermissionDocInfo(
                    doc_id=doc["doc_id"],
                    filename=doc["filename"],
                    title=doc.get("title"),
                )
            )

    return MyPermissionListResponse(data=docs)


@router.get("/permissions/{user_id}", response_model=PermissionListResponse)
async def get_user_permissions(user_id: str, _: dict = Depends(require_admin)):
    """查看某用户的权限列表（管理员）"""
    store = await get_metadata_store()
    perms = await store.get_user_permission_details(user_id)
    return PermissionListResponse(
        data=[
            {
                "user_id": p["user_id"],
                "doc_id": p["doc_id"],
                "granted_by": p["granted_by"],
                "created_at": p["created_at"],
            }
            for p in perms
        ]
    )


@router.post("/permissions", response_model=BaseResponse)
async def grant_permission(
    request: PermissionGrantRequest,
    current_user: dict = Depends(require_admin),
):
    """给用户分配文档权限（管理员）"""
    store = await get_metadata_store()

    user = await store.get_user_by_id(request.user_id)
    if not user:
        return BaseResponse(code=404, message="用户不存在", data=None)

    doc = await store.get_document(request.doc_id)
    if not doc:
        return BaseResponse(code=404, message="文档不存在", data=None)

    ok = await store.grant_doc_permission(
        user_id=request.user_id,
        doc_id=request.doc_id,
        granted_by=current_user["user_id"],
    )
    if not ok:
        return BaseResponse(code=409, message="该权限已存在", data=None)

    return BaseResponse(data={"user_id": request.user_id, "doc_id": request.doc_id})


@router.delete("/permissions", response_model=BaseResponse)
async def revoke_permission(
    user_id: str,
    doc_id: str,
    _: dict = Depends(require_admin),
):
    """取消用户文档权限（管理员）"""
    store = await get_metadata_store()
    ok = await store.revoke_doc_permission(user_id, doc_id)
    if not ok:
        return BaseResponse(code=404, message="权限不存在", data=None)
    return BaseResponse(data={"user_id": user_id, "doc_id": doc_id})


# ---------- 部门管理 ----------

@router.post("/users/{user_id}/department", response_model=BaseResponse)
async def set_user_department(
    user_id: str,
    department: str,
    _: dict = Depends(require_admin),
):
    """设置用户所属部门（管理员）"""
    store = await get_metadata_store()
    user = await store.get_user_by_id(user_id)
    if not user:
        return BaseResponse(code=404, message="用户不存在", data=None)

    ok = await store.update_user_department(user_id, department or None)
    if not ok:
        return BaseResponse(code=500, message="更新失败", data=None)

    return BaseResponse(message=f"已设置用户部门为: {department}")


@router.get("/departments", response_model=BaseResponse)
async def list_departments(_: dict = Depends(require_admin)):
    """列出所有部门"""
    store = await get_metadata_store()
    depts = await store.list_departments()
    return BaseResponse(data=depts)


# ---------- 公共文档权限管理 ----------

@router.post("/documents/{doc_id}/public", response_model=BaseResponse)
async def set_public_document(
    doc_id: str,
    current_user: dict = Depends(require_admin),
):
    """设置文档为所有用户可查询（公共权限）"""
    store = await get_metadata_store()
    doc = await store.get_document(doc_id)
    if not doc:
        return BaseResponse(code=404, message="文档不存在", data=None)

    ok = await store.grant_public_doc_permission(doc_id, current_user["user_id"])
    if not ok:
        return BaseResponse(code=409, message="该文档已经是公共文档", data=None)

    return BaseResponse(message="已设置为公共文档")


@router.delete("/documents/{doc_id}/public", response_model=BaseResponse)
async def revoke_public_document(
    doc_id: str,
    _: dict = Depends(require_admin),
):
    """撤销文档的公共查询权限"""
    store = await get_metadata_store()
    ok = await store.revoke_public_doc_permission(doc_id)
    if not ok:
        return BaseResponse(code=404, message="该文档未设置公共权限", data=None)
    return BaseResponse(message="已撤销公共文档权限")


@router.get("/documents/public", response_model=BaseResponse)
async def list_public_documents(current_user: dict = Depends(get_current_user)):
    """获取所有公共文档列表"""
    store = await get_metadata_store()
    doc_ids = await store.get_public_doc_permissions()

    docs = []
    for doc_id in doc_ids:
        doc = await store.get_document(doc_id)
        if doc:
            docs.append(
                {
                    "doc_id": doc["doc_id"],
                    "filename": doc["filename"],
                    "title": doc.get("title"),
                    "department": doc.get("department"),
                }
            )

    return BaseResponse(data=docs)
