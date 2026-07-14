"""Tests for Conversation Service"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.services.conversation_service import ConversationService
from src.models.conversation import Conversation
from src.models.message import Message
from src.schemas.conversation import ConversationCreate
from src.exceptions import NotFoundException
from src.utils.serialization import attach_count


class TestConversationService:
    """Test cases for ConversationService"""
    
    @pytest.mark.asyncio
    async def test_get_conversations_success(self, db_session: AsyncSession):
        """测试获取对话列表成功"""
        # Create test user and conversations
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        
        # Create conversations
        conv1 = Conversation(
            user_id=user.id,
            title="Test Conversation 1",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        conv2 = Conversation(
            user_id=user.id,
            title="Test Conversation 2",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add_all([conv1, conv2])
        await db_session.commit()
        
        # Get conversations
        conversations, total = await ConversationService.get_conversations(
            db_session, user.id, page=1, page_size=10
        )
        
        # Verify result
        assert total == 2
        assert len(conversations) == 2
        # Check that both conversations are in the result (order might vary)
        titles = [conv["title"] for conv in conversations]
        assert "Test Conversation 1" in titles
        assert "Test Conversation 2" in titles
    
    @pytest.mark.asyncio
    async def test_get_conversations_with_pagination(self, db_session: AsyncSession):
        """测试获取对话列表分页"""
        # Create test user
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        
        # Create 5 conversations
        conversations = []
        for i in range(5):
            conv = Conversation(
                user_id=user.id,
                title=f"Test Conversation {i}",
                summary=None,
                summary_error=False,
                summary_at=None
            )
            conversations.append(conv)
        
        db_session.add_all(conversations)
        await db_session.commit()
        
        # Get first page
        result, total = await ConversationService.get_conversations(
            db_session, user.id, page=1, page_size=2
        )
        
        # Verify pagination
        assert total == 5
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_get_conversations_other_user(self, db_session: AsyncSession):
        """测试获取其他用户的对话（应该看不到）"""
        # Create two users
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        
        # Create conversation for user1
        conv = Conversation(
            user_id=user1.id,
            title="User 1 Conversation",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add(conv)
        await db_session.commit()
        
        # User 2 should see 0 conversations
        conversations, total = await ConversationService.get_conversations(
            db_session, user2.id, page=1, page_size=10
        )
        
        assert total == 0
        assert len(conversations) == 0
    
    @pytest.mark.asyncio
    async def test_create_conversation_success(self, db_session: AsyncSession):
        """测试创建对话成功"""
        # Create test user
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        conversation_data = ConversationCreate(
            title="New Conversation",
            model="deepseek-chat"
        )
        
        result = await ConversationService.create_conversation(
            db_session, user.id, conversation_data
        )
        
        # Verify result
        assert result.user_id == user.id
        assert result.title == "New Conversation"
        assert result.id is not None
    
    @pytest.mark.asyncio
    async def test_get_conversation_success(self, db_session: AsyncSession):
        """测试获取单个对话详情成功"""
        # Create test user and conversation
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        
        conv = Conversation(
            user_id=user.id,
            title="Test Conversation",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add(conv)
        await db_session.commit()
        
        # Get conversation
        result = await ConversationService.get_conversation(
            db_session, conv.id, user.id
        )
        
        # Verify result
        assert result.id == conv.id
        assert result.title == "Test Conversation"
        assert result.user_id == user.id
    
    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, db_session: AsyncSession):
        """测试获取不存在的对话"""
        # Create test user
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        
        # Try to get non-existent conversation
        with pytest.raises(NotFoundException) as exc_info:
            await ConversationService.get_conversation(
                db_session, 999, user.id
            )
        
        assert "对话" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_conversation_wrong_user(self, db_session: AsyncSession):
        """测试获取其他用户的对话（应该失败）"""
        # Create two users
        from src.models.user import User
        from src.utils.security import hash_password
        
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
        
        # Create conversation for user1
        conv = Conversation(
            user_id=user1.id,
            title="User 1 Conversation",
            summary=None,
            summary_error=False,
            summary_at=None
        )
        db_session.add(conv)
        await db_session.commit()
        
        # User 2 tries to get user 1's conversation
        with pytest.raises(NotFoundException) as exc_info:
            await ConversationService.get_conversation(
                db_session, conv.id, user2.id
            )
        
        assert "对话" in str(exc_info.value)
