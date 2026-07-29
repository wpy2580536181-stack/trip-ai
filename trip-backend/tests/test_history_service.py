"""Tests for History Service"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.services.history_service import HistoryService
from src.models.trip import Trip
from src.models.user import User
from src.utils.security import hash_password
from src.exceptions import NotFoundException


class TestHistoryService:
    """Test cases for HistoryService"""
    
    @pytest.mark.asyncio
    async def test_get_trips_success(self, db_session: AsyncSession):
        """测试获取行程历史列表成功"""
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
        
        # Get trips
        trips, total = await HistoryService.get_trips(
            db_session, user.id, page=1, page_size=10
        )
        
        # Verify result
        assert total == 2
        assert len(trips) == 2
    
    @pytest.mark.asyncio
    async def test_get_trips_with_pagination(self, db_session: AsyncSession):
        """测试获取行程历史列表分页"""
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
        
        # Create 5 trips
        trips = []
        for i in range(5):
            trip = Trip(
                user_id=user.id,
                from_city="Beijing",
                city=f"City{i}",
                days=3,
                budget=5000,
                content={"itinerary": []},
                status="completed"
            )
            trips.append(trip)
        
        db_session.add_all(trips)
        await db_session.commit()
        
        # Get first page
        result, total = await HistoryService.get_trips(
            db_session, user.id, page=1, page_size=2
        )
        
        # Verify pagination
        assert total == 5
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_get_trip_success(self, db_session: AsyncSession):
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
        
        # Get trip
        result = await HistoryService.get_trip(
            db_session, trip.id, user.id
        )
        
        # Verify result
        assert result.id == trip.id
        assert result.city == "Shanghai"
        assert result.content == {"itinerary": [{"day": 1, "activities": []}]}
    
    @pytest.mark.asyncio
    async def test_get_trip_not_found(self, db_session: AsyncSession):
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
        
        # Try to get non-existent trip
        with pytest.raises(NotFoundException) as exc_info:
            await HistoryService.get_trip(
                db_session, 999, user.id
            )
        
        assert "行程" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_trip_wrong_user(self, db_session: AsyncSession):
        """测试获取其他用户的行程（应该失败）"""
        # Create two users
        user1 = User(
            username="user1",
            email="user1@example.com",
            password=hash_password("Test@123"),
            nickname="User 1",
            role_id=2,
            status=1
        )
        user2 = User(
            username="user2",
            email="user2@example.com",
            password=hash_password("Test@123"),
            nickname="User 2",
            role_id=2,
            status=1
        )
        db_session.add_all([user1, user2])
        await db_session.commit()
        
        # Create trip for user1
        trip = Trip(
            user_id=user1.id,
            from_city="Beijing",
            city="Shanghai",
            days=3,
            budget=5000,
            content={"itinerary": []},
            status="completed"
        )
        db_session.add(trip)
        await db_session.commit()
        
        # User 2 tries to get user 1's trip
        with pytest.raises(NotFoundException) as exc_info:
            await HistoryService.get_trip(
                db_session, trip.id, user2.id
            )
        
        assert "行程" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_delete_trip_success(self, db_session: AsyncSession):
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
        
        # Delete trip
        result = await HistoryService.delete_trip(
            db_session, trip.id, user.id
        )
        
        # Verify deletion
        assert result is True
        
        # Verify trip is deleted
        from sqlalchemy import select
        result = await db_session.execute(
            select(Trip).where(Trip.id == trip.id)
        )
        deleted_trip = result.scalar_one_or_none()
        assert deleted_trip is None
    
    @pytest.mark.asyncio
    async def test_delete_trip_not_found(self, db_session: AsyncSession):
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
        
        # Try to delete non-existent trip
        with pytest.raises(NotFoundException) as exc_info:
            await HistoryService.delete_trip(
                db_session, 999, user.id
            )
        
        assert "行程" in str(exc_info.value)


class TestGetTripVersions:
    """Fix 5: 完整版本链查询"""

    @staticmethod
    def _make_user(db_session, suffix: str = "") -> User:
        user = User(
            username=f"veruser{suffix}",
            email=f"ver{suffix}@example.com",
            password=hash_password("Test@123"),
            nickname="Version User",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        return user

    @staticmethod
    def _make_trip(db_session, user_id: int, parent_id: int | None = None) -> Trip:
        trip = Trip(
            user_id=user_id,
            city="北京",
            days=3,
            budget=5000,
            content={"city": "北京"},
            status="completed",
            parent_trip_id=parent_id,
        )
        db_session.add(trip)
        return trip

    @pytest.mark.asyncio
    async def test_three_level_chain_from_any_node(self, db_session: AsyncSession):
        """V1→V2→V3 链：从任意节点查都返回完整 3 项且顺序正确"""
        user = self._make_user(db_session)
        await db_session.commit()

        v1 = self._make_trip(db_session, user.id)
        await db_session.commit()
        v2 = self._make_trip(db_session, user.id, parent_id=v1.id)
        await db_session.commit()
        v3 = self._make_trip(db_session, user.id, parent_id=v2.id)
        await db_session.commit()

        # 从链尾、链中、链首分别查询
        for node_id in (v3.id, v2.id, v1.id):
            versions = await HistoryService.get_trip_versions(db_session, node_id, user.id)
            assert [t.id for t in versions] == [v1.id, v2.id, v3.id]

    @pytest.mark.asyncio
    async def test_single_version(self, db_session: AsyncSession):
        """无父无子：只返回自身"""
        user = self._make_user(db_session)
        await db_session.commit()
        trip = self._make_trip(db_session, user.id)
        await db_session.commit()

        versions = await HistoryService.get_trip_versions(db_session, trip.id, user.id)
        assert [t.id for t in versions] == [trip.id]

    @pytest.mark.asyncio
    async def test_sibling_versions_flattened(self, db_session: AsyncSession):
        """同层多子版本（分叉）：按 created_at 升序展平"""
        user = self._make_user(db_session)
        await db_session.commit()

        v1 = self._make_trip(db_session, user.id)
        await db_session.commit()
        v2a = self._make_trip(db_session, user.id, parent_id=v1.id)
        await db_session.commit()
        v2b = self._make_trip(db_session, user.id, parent_id=v1.id)
        await db_session.commit()

        versions = await HistoryService.get_trip_versions(db_session, v2b.id, user.id)
        assert versions[0].id == v1.id
        assert {versions[1].id, versions[2].id} == {v2a.id, v2b.id}

    @pytest.mark.asyncio
    async def test_idor_protection(self, db_session: AsyncSession):
        """其他用户的行程 → NotFoundException"""
        owner = self._make_user(db_session, "owner")
        other = self._make_user(db_session, "other")
        await db_session.commit()

        trip = self._make_trip(db_session, owner.id)
        await db_session.commit()

        with pytest.raises(NotFoundException):
            await HistoryService.get_trip_versions(db_session, trip.id, other.id)

    @pytest.mark.asyncio
    async def test_not_found(self, db_session: AsyncSession):
        """不存在的行程 → NotFoundException"""
        user = self._make_user(db_session)
        await db_session.commit()

        with pytest.raises(NotFoundException):
            await HistoryService.get_trip_versions(db_session, 99999, user.id)
