"""
安全工具：密码哈希 + JWT Token
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

# Fix passlib compatibility with bcrypt >= 4.1 (removes noisy warning)
import bcrypt
if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = type("obj", (object,), {"__version__": bcrypt.__version__})()

from passlib.context import CryptContext

from app.config import get_settings
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# 生产环境启动时校验密钥强度
_default_keys = {
    "enterprise-rag-agent-secret-key-change-me",
    "change-me-in-production-to-a-random-string-at-least-32-chars",
    "",
}
if SECRET_KEY in _default_keys or len(SECRET_KEY) < 32:
    import warnings

    warnings.warn(
        "SECURITY WARNING: SECRET_KEY 使用默认值或长度不足 32 位。"
        "请在 .env 文件中设置强密钥（openssl rand -hex 32），否则 JWT Token 可被伪造。",
        RuntimeWarning,
        stacklevel=2,
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> dict:
    """
    FastAPI 依赖：从 Authorization Header 提取并验证 JWT
    返回用户信息 dict: {user_id, username, role}
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="凭证无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role")

    if not user_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="凭证信息不完整",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": user_id,
        "username": username,
        "role": role,
    }


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI 依赖：要求当前用户必须是管理员
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
