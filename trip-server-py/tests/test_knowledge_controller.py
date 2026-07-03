"""Tests for Knowledge Controller"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.models.spot import Spot


class TestKnowledgeController:
    """Test cases for Knowledge Controller"""
    
    @pytest.mark.asyncio
    async def test_get_spots_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取景点列表成功（公开接口）"""
        # Create spots
        spot1 = Spot(
            name="The Great Wall",
            city="Beijing",
            category="Historical",
            description="Famous historical site",
            tags=["history", "landmark"],
            avg_cost=100.0,
            duration="3 hours",
            open_time="08:00-17:00",
            rating=4.8
        )
        spot2 = Spot(
            name="The Bund",
            city="Shanghai",
            category="Landmark",
            description="Famous waterfront area",
            tags=["landmark"],
            avg_cost=0.0,
            duration="2 hours",
            open_time="24/7",
            rating=4.7
        )
        db_session.add_all([spot1, spot2])
        await db_session.commit()
        
        # Get spots (no auth required)
        response = await async_client.get(
            "/api/knowledge/spots",
            params={"page": 1, "page_size": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 2
        assert len(data["data"]["items"]) == 2
    
    @pytest.mark.asyncio
    async def test_get_spots_with_city_filter(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试按城市筛选景点"""
        # Create spots in different cities
        spot1 = Spot(
            name="The Great Wall",
            city="Beijing",
            category="Historical",
            description="Famous historical site",
            tags=["history"],
            avg_cost=100.0,
            duration="3 hours",
            open_time="08:00-17:00",
            rating=4.8
        )
        spot2 = Spot(
            name="The Bund",
            city="Shanghai",
            category="Landmark",
            description="Famous waterfront area",
            tags=["landmark"],
            avg_cost=0.0,
            duration="2 hours",
            open_time="24/7",
            rating=4.7
        )
        db_session.add_all([spot1, spot2])
        await db_session.commit()
        
        # Get spots filtered by city
        response = await async_client.get(
            "/api/knowledge/spots",
            params={"city": "Beijing", "page": 1, "page_size": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 1
        assert len(data["data"]["items"]) == 1
        assert data["data"]["items"][0]["city"] == "Beijing"
    
    @pytest.mark.asyncio
    async def test_get_spot_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取单个景点详情成功（公开接口）"""
        # Create spot
        spot = Spot(
            name="The Great Wall",
            city="Beijing",
            category="Historical",
            description="Famous historical site",
            tags=["history", "landmark"],
            avg_cost=100.0,
            duration="3 hours",
            open_time="08:00-17:00",
            rating=4.8
        )
        db_session.add(spot)
        await db_session.commit()
        
        # Get spot (no auth required)
        response = await async_client.get(f"/api/knowledge/spots/{spot.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["id"] == spot.id
        assert data["data"]["name"] == "The Great Wall"
        assert data["data"]["city"] == "Beijing"
    
    @pytest.mark.asyncio
    async def test_get_spot_not_found(self, async_client: AsyncClient):
        """测试获取不存在的景点"""
        # Get non-existent spot
        response = await async_client.get("/api/knowledge/spots/999")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_create_spot_unauthorized(self, async_client: AsyncClient):
        """测试未授权创建景点"""
        response = await async_client.post(
            "/api/knowledge/spots",
            json={
                "name": "New Spot",
                "city": "Beijing",
                "category": "Historical",
                "description": "A new spot"
            }
        )
        
        # Should return 401 or 403 (unauthorized or forbidden)
        assert response.status_code in [401, 403]
    
    @pytest.mark.asyncio
    async def test_create_spot_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试创建景点成功（admin）"""
        # Mock require_admin dependency
        from src.middleware.auth import require_admin
        from src.models.user import User
        
        admin_user = User(
            id=1,
            username="admin",
            email="admin@example.com",
            password="hashed",
            nickname="Admin",
            role_id=1,
            status=1
        )
        
        async def mock_require_admin():
            return admin_user
        
        app.dependency_overrides[require_admin] = mock_require_admin
        
        # Create spot
        response = await async_client.post(
            "/api/knowledge/spots",
            json={
                "name": "New Spot",
                "city": "Beijing",
                "category": "Historical",
                "description": "A new spot",
                "tags": ["history"],
                "avg_cost": 100.0,
                "duration": "3 hours",
                "open_time": "08:00-17:00",
                "rating": 4.5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["name"] == "New Spot"
        assert data["message"] == "创建景点成功"
        
        # Clean up
        app.dependency_overrides.pop(require_admin, None)
    
    @pytest.mark.asyncio
    async def test_delete_spot_unauthorized(self, async_client: AsyncClient):
        """测试未授权删除景点"""
        response = await async_client.delete("/api/knowledge/spots/1")
        
        # Should return 401 or 403 (unauthorized or forbidden)
        assert response.status_code in [401, 403]
