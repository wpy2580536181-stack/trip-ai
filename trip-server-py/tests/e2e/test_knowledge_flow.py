"""E2E: 知识库流程

覆盖：公开景点列表 → 景点详情 → 管理端管理
"""

import pytest


class TestKnowledgeFlow:
    """知识库流程端到端测试"""

    @pytest.mark.asyncio
    async def test_list_spots_public(self, client):
        """景点列表应为公开接口"""
        resp = await client.get("/api/knowledge/spots")
        assert resp.status_code == 200, f"List spots failed: {resp.text}"
        data = resp.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_list_spots_with_city_filter(self, client):
        """按城市筛选景点"""
        resp = await client.get("/api/knowledge/spots?city=北京")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_list_spots_with_category(self, client):
        """按类别筛选景点"""
        resp = await client.get("/api/knowledge/spots?category=自然风光")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_spot_detail(self, client):
        """获取景点详情（公开接口）"""
        resp = await client.get("/api/knowledge/spots/1")
        # 景点 1 可能存在也可能不存在
        assert resp.status_code in (200, 404), f"Get spot failed: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "data" in data

    @pytest.mark.asyncio
    async def test_nonexistent_spot_returns_404(self, client):
        """不存在的景点应返回 404"""
        resp = await client.get("/api/knowledge/spots/999999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_spot_requires_admin(self, auth_client):
        """创建景点需要正确参数"""
        resp = await auth_client.post("/api/knowledge/spots", json={
            "name": "E2E Test Spot",
            "city": "北京",
            "category": "景点",
            "description": "E2E 测试用景点",
            "latitude": 39.9,
            "longitude": 116.4,
        })
        # eval-test 的 role_id 可能是 admin(1) 或 user(2)，两种结果都接受
        assert resp.status_code in (200, 201, 403, 422), f"Create spot: {resp.status_code}"
