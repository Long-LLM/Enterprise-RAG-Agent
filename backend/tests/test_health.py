"""
健康检查接口测试
"""
from httpx import AsyncClient


class TestHealth:
    async def test_health_endpoint(self, client: AsyncClient):
        """健康检查接口应返回基础信息"""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "data" in data
        assert "status" in data["data"]

    async def test_health_no_auth_required(self, client: AsyncClient):
        """健康检查无需认证"""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
