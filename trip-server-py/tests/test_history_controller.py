"""Tests for History Controller"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.models.user import User
from src.models.trip import Trip
from src.utils.security import hash_password


class TestHistoryController:
    """Test cases for History Controller"""
    
    @pytest.mark.asyncio
    async def test_get_trips_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取行程历史列表成功"""
        # Create test user and trips
        user = User(
            username="testuser",
            email="test@example.com",
            password=hash_password("Test@123"),
            nickname="Test User",
            role_id=2,
            status=1
        )
        db_session.add(user)
        await db_session.commit()
        
        # Create trips
        trip1 = Trip(
            user_id=user.id,
            from_city="Beijing",
            city="Shanghai",
            days=3,
            budget=5000,
            content={"itinerary": []},
            status="completed"
        )
        trip2 = Trip(
            user_id=user.id,
            from_city="Guangzhou",
            city="Chengdu",
            days=5,
            budget=8000,
            content={"itinerary": []},
            status="completed"
        )
        db_session.add_all([trip1, trip2])
        await db_session.commit()
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Get trips
        response = await async_client.get(
            "/api/history/trips",
            params={"page": 1, "pageSize": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 2
        assert len(data["data"]["items"]) == 2
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_get_trip_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取单个行程详情成功"""
        # Create test user and trip
        user = User(
            username="testuser",
            email="test@example.com",
            password=hash_password("Test@123"),
            nickname="Test User",
            role_id=2,
            status=1
        )
        db_session.add(user)
        await db_session.commit()
        
        trip = Trip(
            user_id=user.id,
            from_city="Beijing",
            city="Shanghai",
            days=3,
            budget=5000,
            content={"itinerary": [{"day": 1, "activities": []}]},
            status="completed"
        )
        db_session.add(trip)
        await db_session.commit()
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Get trip
        response = await async_client.get(f"/api/history/trips/{trip.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["id"] == trip.id
        assert data["data"]["city"] == "Shanghai"
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_get_trip_not_found(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取不存在的行程"""
        # Create test user
        user = User(
            username="testuser",
            email="test@example.com",
            password=hash_password("Test@123"),
            nickname="Test User",
            role_id=2,
            status=1
        )
        db_session.add(user)
        await db_session.commit()
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Get non-existent trip
        response = await async_client.get("/api/history/trips/999")
        
        assert response.status_code == 404
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_delete_trip_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试删除行程成功"""
        # Create test user and trip
        user = User(
            username="testuser",
            email="test@example.com",
            password=hash_password("Test@123"),
            nickname="Test User",
            role_id=2,
            status=1
        )
        db_session.add(user)
        await db_session.commit()
        
        trip = Trip(
            user_id=user.id,
            from_city="Beijing",
            city="Shanghai",
            days=3,
            budget=5000,
            content={"itinerary": []},
            status="completed"
        )
        db_session.add(trip)
        await db_session.commit()
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Delete trip
        response = await async_client.delete(f"/api/history/trips/{trip.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "删除行程成功"
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_delete_trip_not_found(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试删除不存在的行程"""
        # Create test user
        user = User(
            username="testuser",
            email="test@example.com",
            password=hash_password("Test@123"),
            nickname="Test User",
            role_id=2,
            status=1
        )
        db_session.add(user)
        await db_session.commit()
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Delete non-existent trip
        response = await async_client.delete("/api/history/trips/999")
        
        assert response.status_code == 404
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
