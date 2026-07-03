"""Tests for User Service"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.services.user_service import UserService
from src.models.user import User
from src.schemas.user import UserRegister, UserLogin, UserUpdateRequest
from src.exceptions import AppException, NotFoundException
from src.utils.security import hash_password


class TestUserService:
    """Test cases for UserService"""
    
    @pytest.mark.asyncio
    async def test_register_success(self, db_session: AsyncSession):
        """测试用户注册成功"""
        # Prepare test data
        user_data = UserRegister(
            username="newuser",
            email="new@example.com",
            password="Test@123"
        )
        
        # Call service method
        result = await UserService.register(db_session, user_data)
        
        # Verify result
        assert result["username"] == "newuser"
        assert result["email"] == "new@example.com"
        assert "token" in result
        assert "id" in result
        
        # Verify user was created in database
        result = await db_session.execute(
            select(User).where(User.username == "newuser")
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == "new@example.com"
    
    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, db_session: AsyncSession):
        """测试重复用户名注册失败"""
        # Create a user first
        existing_user = User(
            username="existinguser",
            email="existing@example.com",
            password=hash_password("Test@123"),
            nickname="Existing User",
            role_id=2,
            status=1
        )
        db_session.add(existing_user)
        await db_session.commit()
        
        # Try to register with same username
        user_data = UserRegister(
            username="existinguser",
            email="new@example.com",
            password="Test@123"
        )
        
        # Verify exception is raised
        with pytest.raises(AppException) as exc_info:
            await UserService.register(db_session, user_data)
        
        assert exc_info.value.status_code == 400
        assert exc_info.value.error == "ACCOUNT_EXISTS"
    
    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, db_session: AsyncSession):
        """测试重复邮箱注册失败"""
        # Create a user first
        existing_user = User(
            username="user1",
            email="existing@example.com",
            password=hash_password("Test@123"),
            nickname="Existing User",
            role_id=2,
            status=1
        )
        db_session.add(existing_user)
        await db_session.commit()
        
        # Try to register with same email
        user_data = UserRegister(
            username="newuser",
            email="existing@example.com",
            password="Test@123"
        )
        
        # Verify exception is raised
        with pytest.raises(AppException) as exc_info:
            await UserService.register(db_session, user_data)
        
        assert exc_info.value.status_code == 400
        assert exc_info.value.error == "ACCOUNT_EXISTS"
    
    @pytest.mark.asyncio
    async def test_login_success(self, db_session: AsyncSession):
        """测试用户登录成功"""
        # Create a user first
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
        login_data = UserLogin(
            username="testuser",
            password="Test@123"
        )
        
        result = await UserService.login(db_session, login_data)
        
        # Verify result
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert "token" in result
    
    @pytest.mark.asyncio
    async def test_login_with_email(self, db_session: AsyncSession):
        """测试使用邮箱登录"""
        # Create a user first
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
        
        # Login with email
        login_data = UserLogin(
            username="test@example.com",
            password="Test@123"
        )
        
        result = await UserService.login(db_session, login_data)
        
        # Verify result
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, db_session: AsyncSession):
        """测试错误密码登录失败"""
        # Create a user first
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
        login_data = UserLogin(
            username="testuser",
            password="WrongPassword"
        )
        
        # Verify exception is raised
        with pytest.raises(AppException) as exc_info:
            await UserService.login(db_session, login_data)
        
        assert exc_info.value.status_code == 401
        assert exc_info.value.error == "WRONG_PASSWORD"
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, db_session: AsyncSession):
        """测试根据ID获取用户成功"""
        # Create a user first
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
        
        # Get user by ID
        result = await UserService.get_user_by_id(db_session, user.id)
        
        # Verify result
        assert result.id == user.id
        assert result.username == "testuser"
        assert result.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        """测试获取不存在的用户"""
        # Verify exception is raised
        with pytest.raises(NotFoundException) as exc_info:
            await UserService.get_user_by_id(db_session, 999)
        
        assert "用户" in str(exc_info.value)
