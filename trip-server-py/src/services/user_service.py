"""User service (business logic)"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from src.models.user import User
from src.models.role import Role
from src.models.password_reset import PasswordReset
from src.schemas.user import (
    UserRegister, UserLogin, UserUpdateRequest
)
from src.utils.security import (
    hash_password, verify_password, create_access_token
)
from src.exceptions import (
    AppException, NotFoundException, UnauthorizedException
)

logger = logging.getLogger(__name__)


class UserService:
    """User service (business logic)"""
    
    @staticmethod
    async def register(db: AsyncSession, data: UserRegister) -> dict:
        """注册新用户
        
        Args:
            db: Database session
            data: Registration data (username, email, password)
            
        Returns:
            dict: User info + JWT token
            
        Raises:
            AppException: if username or email already exists
        """
        # 1. Check if username or email already exists
        result = await db.execute(
            select(User).where(
                or_(User.username == data.username, User.email == data.email)
            )
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise AppException(
                status_code=400,
                message="该账号已存在",
                error="ACCOUNT_EXISTS"
            )
        
        # 2. Hash password
        hashed_password = hash_password(data.password)
        
        # 3. Create user (default role_id=2, status=1)
        user = User(
            username=data.username,
            email=data.email,
            password=hashed_password,
            nickname=data.username,  # Use username as initial nickname
            role_id=2,  # USER role
            status=1  # Active
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        # 4. Generate JWT token
        token = create_access_token(user.id, user.username, user.role_id)
        
        # 5. Return user info + token
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "roleId": user.role_id,
            "token": token
        }
    
    @staticmethod
    async def login(db: AsyncSession, data: UserLogin) -> dict:
        """登录（返回 User + JWT）
        
        Args:
            db: Database session
            data: Login data (username/email, password)
            
        Returns:
            dict: User info + JWT token
            
        Raises:
            AppException: if user not found, disabled, or password incorrect
        """
        # 1. Find user by username or email
        result = await db.execute(
            select(User).where(
                or_(User.username == data.username, User.email == data.username)
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise AppException(
                status_code=401,
                message="用户不存在",
                error="USER_NOT_FOUND"
            )
        
        # 2. Check if account is disabled
        if user.status == 0:
            raise AppException(
                status_code=403,
                message="账号已被禁用",
                error="ACCOUNT_DISABLED"
            )
        
        # 3. Verify password
        if not verify_password(data.password, user.password):
            raise AppException(
                status_code=401,
                message="密码错误",
                error="WRONG_PASSWORD"
            )
        
        # 4. Generate JWT token
        token = create_access_token(user.id, user.username, user.role_id)
        
        # 5. Return user info + token
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "phone": user.phone,
            "bio": user.bio,
            "roleId": user.role_id,
            "token": token
        }
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
        """根据 ID 获取用户
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            User: User object
            
        Raises:
            NotFoundException: if user not found
        """
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundException("用户")
        
        return user
    
    @staticmethod
    async def get_user_info(db: AsyncSession, user_id: int) -> dict:
        """获取用户信息（返回字典，不含密码）
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            dict: User info (without password)
            
        Raises:
            NotFoundException: if user not found
        """
        user = await UserService.get_user_by_id(db, user_id)
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "phone": user.phone,
            "bio": user.bio,
            "roleId": user.role_id,
            "status": user.status,
            "createdAt": user.created_at,
            "updatedAt": user.updated_at
        }
    
    @staticmethod
    async def update_user_info(
        db: AsyncSession, 
        user_id: int, 
        data: UserUpdateRequest
    ) -> dict:
        """更新用户信息
        
        Args:
            db: Database session
            user_id: User ID
            data: Update data (nickname, avatar, phone, bio, preferences)
            
        Returns:
            dict: Updated user info
            
        Raises:
            NotFoundException: if user not found
        """
        user = await UserService.get_user_by_id(db, user_id)
        
        # Update fields if provided
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)
        
        await db.commit()
        await db.refresh(user)
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "nickname": user.nickname,
            "avatar": user.avatar,
            "phone": user.phone,
            "bio": user.bio,
            "roleId": user.role_id,
            "preferences": user.preferences
        }
    
    @staticmethod
    async def change_password(
        db: AsyncSession, 
        user_id: int, 
        old_password: str, 
        new_password: str
    ) -> bool:
        """修改密码
        
        Args:
            db: Database session
            user_id: User ID
            old_password: Old password
            new_password: New password
            
        Returns:
            bool: True if successful
            
        Raises:
            NotFoundException: if user not found
            AppException: if old password is incorrect
        """
        # 1. Find user
        user = await UserService.get_user_by_id(db, user_id)
        
        # 2. Verify old password
        if not verify_password(old_password, user.password):
            raise AppException(
                status_code=401,
                message="原密码错误",
                error="WRONG_OLD_PASSWORD"
            )
        
        # 3. Hash new password
        hashed_password = hash_password(new_password)
        
        # 4. Update password
        user.password = hashed_password
        await db.commit()
        
        return True
    
    @staticmethod
    async def forgot_password(db: AsyncSession, email: str) -> bool:
        """忘记密码（生成重置令牌）
        
        Security: Always returns True to prevent user enumeration
        
        Args:
            db: Database session
            email: User email
            
        Returns:
            bool: True (always, for security)
        """
        from src.models.password_reset import PasswordReset
        
        # 1. Find user by email (silently ignore if not found)
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Security: log warning but return success
            logger.warning(f"Password reset requested but email not found: {email}")
            return True
        
        # 2. Create password reset token
        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        
        password_reset = PasswordReset(
            email=email,
            token=token,
            expires_at=expires_at,
            used=False
        )
        
        db.add(password_reset)
        await db.commit()
        
        # TODO: Send email with reset link
        # For now, just log the token (in production, this should be sent via email)
        logger.info(f"Password reset token generated for {email}: {token}")
        
        return True
    
    @staticmethod
    async def reset_password(
        db: AsyncSession, 
        email: str, 
        token: str, 
        new_password: str
    ) -> bool:
        """重置密码
        
        Args:
            db: Database session
            email: User email
            token: Reset token
            new_password: New password
            
        Returns:
            bool: True if successful
            
        Raises:
            AppException: if token is invalid or expired
        """
        # 1. Find valid reset token
        result = await db.execute(
            select(PasswordReset).where(
                PasswordReset.email == email,
                PasswordReset.token == token,
                PasswordReset.used == False,
                PasswordReset.expires_at > datetime.utcnow()
            )
        )
        reset_record = result.scalar_one_or_none()
        
        if not reset_record:
            raise AppException(
                status_code=400,
                message="重置链接无效或已过期",
                error="INVALID_RESET_TOKEN"
            )
        
        # 2. Find user by email
        user_result = await db.execute(
            select(User).where(User.email == email)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise AppException(
                status_code=404,
                message="用户不存在",
                error="USER_NOT_FOUND"
            )
        
        # 3. Hash new password
        hashed_password = hash_password(new_password)
        
        # 4. Update user password
        user.password = hashed_password
        
        # 5. Mark token as used
        reset_record.used = True
        
        await db.commit()
        
        return True
