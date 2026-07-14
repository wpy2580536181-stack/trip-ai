"""Tests for Conversation Controller"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.models.user import User
from src.models.conversation import Conversation
from src.utils.security import hash_password


class TestConversationController:
    """Test cases for Conversation Controller"""
    
    @pytest.mark.asyncio
    async def test_create_conversation_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试创建对话成功"""
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
        
        # Create conversation
        response = await async_client.post(
            "/api/conversations",
            json={
                "title": "Test Conversation",
                "model": "deepseek-chat"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["title"] == "Test Conversation"
        assert data["message"] == "创建对话成功"
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_get_conversations_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取对话列表成功"""
        # Create test user and conversations
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
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Get conversations
        response = await async_client.get(
            "/api/conversations",
            params={"page": 1, "page_size": 10}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total"] == 2
        assert len(data["data"]["items"]) == 2
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_get_conversation_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试获取单个对话详情成功"""
        # Create test user and conversation
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
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Get conversation
        response = await async_client.get(f"/api/conversations/{conv.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["id"] == conv.id
        assert data["data"]["title"] == "Test Conversation"
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_delete_conversation_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试删除对话成功"""
        # Create test user and conversation
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
        
        # Mock get_current_user dependency
        from src.middleware.auth import get_current_user
        async def mock_get_current_user():
            return user
        
        app.dependency_overrides[get_current_user] = mock_get_current_user
        
        # Delete conversation
        response = await async_client.delete(f"/api/conversations/{conv.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "删除对话成功"
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
    
    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, async_client: AsyncClient, db_session: AsyncSession):
        """测试删除不存在的对话"""
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
        
        # Delete non-existent conversation
        response = await async_client.delete("/api/conversations/999")
        
        assert response.status_code == 404
        
        # Clean up
        app.dependency_overrides.pop(get_current_user, None)
