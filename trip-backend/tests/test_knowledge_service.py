"""Tests for Knowledge Service"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.services.knowledge_service import KnowledgeService
from src.models.spot import Spot
from src.schemas.knowledge import SpotCreate, SpotUpdate
from src.exceptions import NotFoundException


class TestKnowledgeService:
    """Test cases for KnowledgeService"""
    
    @pytest.mark.asyncio
    async def test_get_spots_success(self, db_session: AsyncSession):
        """测试获取景点列表成功"""
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
            name="The Forbidden City",
            city="Beijing",
            category="Historical",
            description="Imperial palace",
            tags=["history", "culture"],
            avg_cost=60.0,
            duration="4 hours",
            open_time="08:30-17:00",
            rating=4.9
        )
        db_session.add_all([spot1, spot2])
        await db_session.commit()
        
        # Get spots
        spots, total = await KnowledgeService.get_spots(
            db_session, city=None, category=None, page=1, page_size=10
        )
        
        # Verify result
        assert total == 2
        assert len(spots) == 2
    
    @pytest.mark.asyncio
    async def test_get_spots_with_city_filter(self, db_session: AsyncSession):
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
        spots, total = await KnowledgeService.get_spots(
            db_session, city="Beijing", category=None, page=1, page_size=10
        )
        
        # Verify filter
        assert total == 1
        assert len(spots) == 1
        assert spots[0].city == "Beijing"
    
    @pytest.mark.asyncio
    async def test_get_spots_with_pagination(self, db_session: AsyncSession):
        """测试获取景点列表分页"""
        # Create 5 spots
        spots = []
        for i in range(5):
            spot = Spot(
                name=f"Spot {i}",
                city="Beijing",
                category="Historical",
                description=f"Description {i}",
                tags=["history"],
                avg_cost=100.0,
                duration="3 hours",
                open_time="08:00-17:00",
                rating=4.5
            )
            spots.append(spot)
        
        db_session.add_all(spots)
        await db_session.commit()
        
        # Get first page
        result, total = await KnowledgeService.get_spots(
            db_session, city=None, category=None, page=1, page_size=2
        )
        
        # Verify pagination
        assert total == 5
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_get_spot_success(self, db_session: AsyncSession):
        """测试获取单个景点详情成功"""
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
        
        # Get spot
        result = await KnowledgeService.get_spot(db_session, spot.id)
        
        # Verify result
        assert result.id == spot.id
        assert result.name == "The Great Wall"
        assert result.city == "Beijing"
        assert result.rating == 4.8
    
    @pytest.mark.asyncio
    async def test_get_spot_not_found(self, db_session: AsyncSession):
        """测试获取不存在的景点"""
        # Try to get non-existent spot
        with pytest.raises(NotFoundException) as exc_info:
            await KnowledgeService.get_spot(db_session, 999)
        
        assert "景点" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_spot_success(self, db_session: AsyncSession):
        """测试创建景点成功"""
        # Create spot data
        spot_data = SpotCreate(
            name="New Spot",
            city="Shanghai",
            category="Modern",
            description="A new spot",
            tags=["modern", "landmark"],
            avg_cost=50.0,
            duration="2 hours",
            open_time="09:00-18:00",
            rating=4.5
        )
        
        # Create spot
        result = await KnowledgeService.create_spot(db_session, spot_data)
        
        # Verify result
        assert result.name == "New Spot"
        assert result.city == "Shanghai"
        assert result.category == "Modern"
        assert result.rating == 4.5
        
        # Verify spot was created in database
        from sqlalchemy import select
        db_result = await db_session.execute(
            select(Spot).where(Spot.name == "New Spot")
        )
        created_spot = db_result.scalar_one_or_none()
        assert created_spot is not None
        assert created_spot.city == "Shanghai"
    
    @pytest.mark.asyncio
    async def test_update_spot_success(self, db_session: AsyncSession):
        """测试更新景点成功"""
        # Create spot
        spot = Spot(
            name="Old Name",
            city="Beijing",
            category="Historical",
            description="Old description",
            tags=["history"],
            avg_cost=100.0,
            duration="3 hours",
            open_time="08:00-17:00",
            rating=4.5
        )
        db_session.add(spot)
        await db_session.commit()
        
        # Update spot
        update_data = SpotUpdate(
            name="New Name",
            description="New description",
            rating=4.8
        )
        
        result = await KnowledgeService.update_spot(db_session, spot.id, update_data)
        
        # Verify result
        assert result.name == "New Name"
        assert result.description == "New description"
        assert result.rating == 4.8
        assert result.city == "Beijing"  # Unchanged field
    
    @pytest.mark.asyncio
    async def test_update_spot_not_found(self, db_session: AsyncSession):
        """测试更新不存在的景点"""
        # Try to update non-existent spot
        update_data = SpotUpdate(
            name="New Name"
        )
        
        with pytest.raises(NotFoundException) as exc_info:
            await KnowledgeService.update_spot(db_session, 999, update_data)
        
        assert "景点" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_delete_spot_success(self, db_session: AsyncSession):
        """测试删除景点成功"""
        # Create spot
        spot = Spot(
            name="To Delete",
            city="Beijing",
            category="Historical",
            description="Will be deleted",
            tags=["history"],
            avg_cost=100.0,
            duration="3 hours",
            open_time="08:00-17:00",
            rating=4.5
        )
        db_session.add(spot)
        await db_session.commit()
        
        # Delete spot
        result = await KnowledgeService.delete_spot(db_session, spot.id)
        
        # Verify deletion
        assert result is True
        
        # Verify spot is deleted
        from sqlalchemy import select
        db_result = await db_session.execute(
            select(Spot).where(Spot.id == spot.id)
        )
        deleted_spot = db_result.scalar_one_or_none()
        assert deleted_spot is None
    
    @pytest.mark.asyncio
    async def test_delete_spot_not_found(self, db_session: AsyncSession):
        """测试删除不存在的景点"""
        # Try to delete non-existent spot
        with pytest.raises(NotFoundException) as exc_info:
            await KnowledgeService.delete_spot(db_session, 999)
        
        assert "景点" in str(exc_info.value)
