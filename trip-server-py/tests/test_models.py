"""Tests for Database Models"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.trip import Trip
from src.models.spot import Spot
from src.models.role import Role
from src.models.password_reset import PasswordReset
from src.utils.security import hash_password


class TestUserModel:
    """Test cases for User model"""
    
    @pytest.mark.asyncio
    async def test_create_user(self, db_session: AsyncSession):
        """测试创建用户"""
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
        
        # Verify user was created
        result = await db_session.execute(
            select(User).where(User.username == "testuser")
        )
        created_user = result.scalar_one_or_none()
        
        assert created_user is not None
        assert created_user.username == "testuser"
        assert created_user.email == "test@example.com"
        assert created_user.role_id == 2
        assert created_user.status == 1
    
    @pytest.mark.asyncio
    async def test_user_created_at(self, db_session: AsyncSession):
        """测试用户创建时间自动设置"""
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
        
        # Verify created_at is set
        assert user.created_at is not None
        
        # Verify updated_at is None (as configured in base.py)
        assert user.updated_at is None


class TestConversationModel:
    """Test cases for Conversation model"""
    
    @pytest.mark.asyncio
    async def test_create_conversation(self, db_session: AsyncSession):
        """测试创建对话"""
        # Create user first
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
        
        # Create conversation
        conversation = Conversation(
            user_id=user.id,
            title="Test Conversation",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add(conversation)
        await db_session.commit()
        
        # Verify conversation was created
        result = await db_session.execute(
            select(Conversation).where(Conversation.title == "Test Conversation")
        )
        created_conversation = result.scalar_one_or_none()
        
        assert created_conversation is not None
        assert created_conversation.user_id == user.id
        assert created_conversation.title == "Test Conversation"
    
    @pytest.mark.asyncio
    async def test_conversation_user_relationship(self, db_session: AsyncSession):
        """测试对话与用户的关系"""
        # Create user first
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
        
        # Create conversation
        conversation = Conversation(
            user_id=user.id,
            title="Test Conversation",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add(conversation)
        await db_session.commit()
        
        # Query conversation with user relationship
        result = await db_session.execute(
            select(Conversation).where(Conversation.id == conversation.id)
        )
        conv = result.scalar_one_or_none()
        
        # Verify relationship (need to load user)
        from sqlalchemy.orm import selectinload
        result = await db_session.execute(
            select(Conversation)
            .where(Conversation.id == conversation.id)
            .options(selectinload(Conversation.user))
        )
        conv_with_user = result.scalar_one_or_none()
        
        assert conv_with_user.user is not None
        assert conv_with_user.user.username == "testuser"


class TestMessageModel:
    """Test cases for Message model"""
    
    @pytest.mark.asyncio
    async def test_create_message(self, db_session: AsyncSession):
        """测试创建消息"""
        # Create user and conversation first
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
        
        conversation = Conversation(
            user_id=user.id,
            title="Test Conversation",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add(conversation)
        await db_session.commit()
        
        # Create message
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content="Hello, world!"
        )
        db_session.add(message)
        await db_session.commit()
        
        # Verify message was created
        result = await db_session.execute(
            select(Message).where(Message.conversation_id == conversation.id)
        )
        created_message = result.scalar_one_or_none()
        
        assert created_message is not None
        assert created_message.role == "user"
        assert created_message.content == "Hello, world!"
        assert created_message.excluded_from_context == False


class TestTripModel:
    """Test cases for Trip model"""
    
    @pytest.mark.asyncio
    async def test_create_trip(self, db_session: AsyncSession):
        """测试创建行程"""
        # Create user first
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
        
        # Create trip
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
        
        # Verify trip was created
        result = await db_session.execute(
            select(Trip).where(Trip.user_id == user.id)
        )
        created_trip = result.scalar_one_or_none()
        
        assert created_trip is not None
        assert created_trip.from_city == "Beijing"
        assert created_trip.city == "Shanghai"
        assert created_trip.days == 3
        assert created_trip.budget == 5000
        assert created_trip.status == "completed"
        assert created_trip.content == {"itinerary": [{"day": 1, "activities": []}]}


class TestSpotModel:
    """Test cases for Spot model"""
    
    @pytest.mark.asyncio
    async def test_create_spot(self, db_session: AsyncSession):
        """测试创建景点"""
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
        
        # Verify spot was created
        result = await db_session.execute(
            select(Spot).where(Spot.name == "The Great Wall")
        )
        created_spot = result.scalar_one_or_none()
        
        assert created_spot is not None
        assert created_spot.name == "The Great Wall"
        assert created_spot.city == "Beijing"
        assert created_spot.category == "Historical"
        assert created_spot.rating == 4.8
        assert created_spot.tags == ["history", "landmark"]
