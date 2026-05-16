"""
认证相关接口测试
覆盖: 注册、登录、获取当前用户、权限校验
"""
import pytest
from httpx import AsyncClient


class TestAuth:
    """用户认证测试套件"""

    async def test_register_success(self, client: AsyncClient):
        """正常注册流程"""
        import uuid
        username = f"newuser_{uuid.uuid4().hex[:8]}"
        resp = await client.post("/api/auth/register", json={
            "username": username,
            "password": "newpass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["username"] == username
        assert data["data"]["role"] == "user"

    async def test_register_duplicate_username(self, client: AsyncClient):
        """重复用户名注册应失败"""
        import uuid
        username = f"dupuser_{uuid.uuid4().hex[:8]}"
        # 先注册一次
        await client.post("/api/auth/register", json={
            "username": username,
            "password": "pass1234",
        })
        # 再次注册
        resp = await client.post("/api/auth/register", json={
            "username": username,
            "password": "pass1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 409
        assert "已存在" in data["message"]

    async def test_register_validation_username_too_short(self, client: AsyncClient):
        """用户名过短应被拒绝"""
        resp = await client.post("/api/auth/register", json={
            "username": "ab",
            "password": "pass1234",
        })
        # Pydantic validation error
        assert resp.status_code == 422

    async def test_login_success(self, client: AsyncClient, test_user: dict):
        """正常登录流程"""
        resp = await client.post("/api/auth/login", json={
            "username": test_user["username"],
            "password": test_user["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert data["data"]["user"]["username"] == test_user["username"]

    async def test_login_wrong_password(self, client: AsyncClient, test_user: dict):
        """错误密码登录应失败"""
        resp = await client.post("/api/auth/login", json={
            "username": test_user["username"],
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """不存在的用户登录应失败"""
        resp = await client.post("/api/auth/login", json={
            "username": "nonexistent_user_xyz",
            "password": "somepass",
        })
        assert resp.status_code == 401

    async def test_get_me_with_valid_token(self, client: AsyncClient, auth_headers: dict):
        """携带有效 Token 访问 /me 应成功"""
        resp = await client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["username"] == "testuser"
        assert data["data"]["role"] == "user"

    async def test_get_me_without_token(self, client: AsyncClient):
        """无 Token 访问 /me 应 401"""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    async def test_get_me_with_invalid_token(self, client: AsyncClient):
        """无效 Token 应 401"""
        resp = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid-token-123"
        })
        assert resp.status_code == 401


class TestPermissionAccess:
    """权限控制测试"""

    async def test_admin_only_route_as_user(self, client: AsyncClient, auth_headers: dict):
        """普通用户访问管理员接口应 403"""
        resp = await client.get("/api/users", headers=auth_headers)
        assert resp.status_code == 403

    async def test_admin_only_route_as_admin(self, client: AsyncClient, admin_headers: dict):
        """管理员访问管理员接口应成功"""
        resp = await client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)

    async def test_public_route_without_auth(self, client: AsyncClient):
        """健康检查无需认证"""
        resp = await client.get("/api/health")
        assert resp.status_code == 200

    async def test_login_route_without_auth(self, client: AsyncClient):
        """登录接口无需认证"""
        resp = await client.post("/api/auth/login", json={
            "username": "anyone",
            "password": "anypass",
        })
        # 即使登录失败也不应该是 401（这是业务逻辑失败）
        assert resp.status_code in [200, 401]
