"""Tests for User Controller"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from src.schemas.user import UserRegister, UserLogin


class TestUserController:
    """Test cases for User Controller"""
    
    @pytest.mark.asyncio
    async def test_register_success(self, async_client: AsyncClient):
        """测试用户注册成功"""
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "password": "Test@123",
                "email": "test@example.com"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["username"] == "testuser"
        assert data["data"]["email"] == "test@example.com"
        assert "token" in data["data"]
        assert data["message"] == "注册成功"
    
    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, async_client: AsyncClient, db_session):
        """测试重复用户名注册失败"""
        # Create a user first
        from src.models.user import User
        from src.utils.security import hash_password
        
        existing_user = User(
            username="testuser",
            email="existing@example.com",
            password=hash_password("Test@123"),
            nickname="Existing User",
            role_id=2,
            status=1
        )
        db_session.add(existing_user)
        await db_session.commit()
        
        # Try to register with same username
        response = await async_client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "password": "Test@123",
                "email": "new@example.com"
            }
        )
        
        # Controller uses HTTPException with detail wrapper
        assert response.status_code == 400
        data = response.json()
        # Note: HTTPException wraps detail in "detail" field
        assert "detail" in data
        assert data["detail"]["code"] == 400
        assert data["detail"]["error"] == "REGISTRATION_FAILED"
    
    @pytest.mark.asyncio
    async def test_login_success(self, async_client: AsyncClient, db_session):
        """测试用户登录成功"""
        # Create a user first
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
        
        # Login
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "Test@123"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["username"] == "testuser"
        assert "token" in data["data"]
    
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient, db_session):
        """测试错误密码登录失败"""
        # Create a user first
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
        
        # Login with wrong password
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "WrongPassword"
            }
        )
        
        # Controller uses HTTPException with detail wrapper
        assert response.status_code == 401
        data = response.json()
        # Note: HTTPException wraps detail in "detail" field
        assert "detail" in data
        assert data["detail"]["code"] == 401
        assert data["detail"]["error"] == "LOGIN_FAILED"
    
    @pytest.mark.asyncio
    async def test_get_user_info_unauthorized(self, async_client: AsyncClient):
        """测试未授权获取用户信息"""
        response = await async_client.get("/api/auth/me")
        
        # Should return 401 (unauthorized)
        # The detail is a string, not a dict
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
        # detail can be a string like "Not authenticated"
        assert isinstance(data["detail"], str)
    
    @pytest.mark.asyncio
    async def test_forgot_password(self, async_client: AsyncClient):
        """测试忘记密码"""
        response = await async_client.post(
            "/api/auth/reset-password",
            json={
                "email": "test@example.com"
            }
        )
        
        # Should always return success (security)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "重置密码邮件已发送"
