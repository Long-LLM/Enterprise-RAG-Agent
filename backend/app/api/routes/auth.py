"""
用户鉴权接口
- POST /api/auth/register  用户注册
- POST /api/auth/login     用户登录
- GET  /api/auth/me        获取当前用户信息
"""
import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_metadata_store
from app.core.security import create_access_token, get_current_user, get_password_hash, verify_password
from app.models.schemas import BaseResponse, TokenResponse, UserInfo, UserLoginRequest, UserRegisterRequest

router = APIRouter(tags=["Auth"])


@router.post("/auth/register", response_model=BaseResponse)
async def register(request: UserRegisterRequest):
    """用户注册（默认角色为 user）"""
    store = await get_metadata_store()

    # 检查用户名是否已存在
    existing = await store.get_user_by_username(request.username)
    if existing:
        return BaseResponse(code=409, message="用户名已存在", data=None)

    user_id = uuid.uuid4().hex[:16]
    password_hash = get_password_hash(request.password)
    await store.create_user(
        user_id=user_id,
        username=request.username,
        password_hash=password_hash,
        role="user",
    )

    return BaseResponse(
        data=UserInfo(
            user_id=user_id,
            username=request.username,
            role="user",
        ).model_dump()
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: UserLoginRequest):
    """用户登录，返回 JWT Token"""
    from fastapi import HTTPException, status
    store = await get_metadata_store()
    user = await store.get_user_by_username(request.username)

    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={
            "sub": user["user_id"],
            "username": user["username"],
            "role": user["role"],
            "department": user.get("department"),
        }
    )

    return TokenResponse(
        data=TokenResponse.TokenData(
            access_token=access_token,
            token_type="bearer",
            user=UserInfo(
                user_id=user["user_id"],
                username=user["username"],
                role=user["role"],
                department=user.get("department"),
                created_at=user["created_at"],
            ),
        )
    )


@router.get("/auth/me", response_model=BaseResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return BaseResponse(
        data=UserInfo(
            user_id=current_user["user_id"],
            username=current_user["username"],
            role=current_user["role"],
            department=current_user.get("department"),
        ).model_dump()
    )
