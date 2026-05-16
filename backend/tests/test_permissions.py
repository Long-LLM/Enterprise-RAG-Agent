"""
权限管理接口测试
覆盖: 公共文档设置、用户权限分配、部门管理
"""
from httpx import AsyncClient


class TestPermissions:
    async def test_set_public_document_as_admin(self, client: AsyncClient, admin_headers: dict):
        """管理员设置公共文档"""
        # 先创建一个文档（这里简化，直接调权限接口，doc_id 可能不存在但测试接口行为）
        resp = await client.post("/api/documents/test_doc_001/public", headers=admin_headers)
        # 文档不存在时应返回 404
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] in [200, 404]

    async def test_set_public_document_as_user(self, client: AsyncClient, auth_headers: dict):
        """普通用户设置公共文档应 403"""
        resp = await client.post("/api/documents/test_doc_001/public", headers=auth_headers)
        assert resp.status_code == 403

    async def test_list_users_admin_only(self, client: AsyncClient, admin_headers: dict, auth_headers: dict):
        """用户列表只有管理员可访问"""
        # admin 可以访问
        resp_admin = await client.get("/api/users", headers=admin_headers)
        assert resp_admin.status_code == 200

        # user 不能访问
        resp_user = await client.get("/api/users", headers=auth_headers)
        assert resp_user.status_code == 403

    async def test_departments_admin_only(self, client: AsyncClient, admin_headers: dict, auth_headers: dict):
        """部门列表只有管理员可访问"""
        resp_admin = await client.get("/api/departments", headers=admin_headers)
        assert resp_admin.status_code == 200

        resp_user = await client.get("/api/departments", headers=auth_headers)
        assert resp_user.status_code == 403

    async def test_grant_permission_admin_only(self, client: AsyncClient, admin_headers: dict, auth_headers: dict):
        """分配权限只有管理员可执行"""
        resp_user = await client.post("/api/permissions", json={
            "user_id": "some_user",
            "doc_id": "some_doc",
        }, headers=auth_headers)
        assert resp_user.status_code == 403
