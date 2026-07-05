"""User controller (HTTP handlers)"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict
from fastapi import Query

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.middleware.rate_limiter import auth_rate_limiter
from src.schemas.user import (
    UserRegister, UserLogin, UserResponse, 
    UserUpdateRequest, ChangePasswordRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
    LoginResponse
)
from src.services.user_service import UserService
from src.models.user import User

router = APIRouter(
    prefix="/user",
    tags=["Authentication"],
    dependencies=[Depends(auth_rate_limiter)],
)


@router.post(
    "/register",
    response_model=Dict,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
    description="""
    注册新用户账号。
    
    请求体必须包含：
    - username: 用户名（3-50字符）
    - email: 邮箱地址
    - password: 密码（6-50字符）
    
    返回用户信息和JWT token。
    
    错误响应：
    - 400: 用户名或邮箱已存在
    - 422: 请求参数验证失败
    """
)
async def register(
    data: UserRegister, 
    db: AsyncSession = Depends(get_db)
):
    """用户注册
    
    Args:
        data: 注册数据（username, email, password）
        db: 数据库会话
        
    Returns:
        dict: 包含用户信息和token的响应
        
    Raises:
        HTTPException: 400 如果用户名或邮箱已存在
    """
    try:
        result = await UserService.register(db, data)
        
        return {
            "code": 200,
            "data": result,
            "message": "注册成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "data": None,
                "message": str(e),
                "error": "REGISTRATION_FAILED"
            }
        )


@router.post(
    "/login",
    response_model=Dict,
    summary="用户登录",
    description="""
    用户登录，支持用户名或邮箱登录。
    
    请求体必须包含：
    - username: 用户名或邮箱
    - password: 密码
    
    返回用户信息和JWT token。
    
    错误响应：
    - 401: 用户不存在或密码错误
    - 403: 账号已被禁用
    - 422: 请求参数验证失败
    """
)
async def login(
    data: UserLogin, 
    db: AsyncSession = Depends(get_db)
):
    """用户登录
    
    Args:
        data: 登录数据（username/email, password）
        db: 数据库会话
        
    Returns:
        dict: 包含用户信息和token的响应
        
    Raises:
        HTTPException: 401 如果用户不存在或密码错误
        HTTPException: 403 如果账号已被禁用
    """
    try:
        result = await UserService.login(db, data)
        
        return {
            "code": 200,
            "data": result,
            "message": "登录成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail={
                "code": 401,
                "data": None,
                "message": str(e),
                "error": "LOGIN_FAILED"
            }
        )


@router.get(
    "/info",
    response_model=Dict,
    summary="获取当前用户信息",
    description="""
    获取当前登录用户的详细信息。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    返回用户基本信息（不含密码）。
    
    错误响应：
    - 401: 未授权或token已过期
    - 404: 用户不存在
    """
)
async def get_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户信息
    
    Args:
        current_user: 当前认证用户（从JWT中提取）
        db: 数据库会话
        
    Returns:
        dict: 包含用户信息的响应
        
    Raises:
        HTTPException: 401 如果未授权
        HTTPException: 404 如果用户不存在
    """
    try:
        user_info = await UserService.get_user_info(db, current_user.id)
        
        return {
            "code": 200,
            "data": user_info,
            "message": "获取用户信息成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "data": None,
                "message": str(e),
                "error": "GET_USER_INFO_FAILED"
            }
        )


@router.put(
    "/info",
    response_model=Dict,
    summary="更新用户信息",
    description="""
    更新当前登录用户的信息。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    请求体可包含（可选字段）：
    - nickname: 昵称
    - avatar: 头像URL
    - phone: 手机号
    - bio: 个人简介
    - preferences: 偏好设置（JSON对象）
    
    错误响应：
    - 401: 未授权或token已过期
    - 404: 用户不存在
    """
)
async def update_user_info(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新用户信息
    
    Args:
        data: 更新数据（nickname, avatar, phone, bio, preferences）
        current_user: 当前认证用户（从JWT中提取）
        db: 数据库会话
        
    Returns:
        dict: 包含更新后用户信息的响应
    """
    try:
        result = await UserService.update_user_info(db, current_user.id, data)
        
        return {
            "code": 200,
            "data": result,
            "message": "更新用户信息成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "data": None,
                "message": str(e),
                "error": "UPDATE_USER_INFO_FAILED"
            }
        )


@router.put(
    "/password",
    response_model=Dict,
    summary="修改密码",
    description="""
    修改当前登录用户的密码。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    请求体必须包含：
    - oldPassword: 旧密码
    - newPassword: 新密码（6-50字符）
    
    错误响应：
    - 401: 未授权或token已过期
    - 401: 旧密码错误
    - 404: 用户不存在
    """
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """修改密码
    
    Args:
        data: 修改密码数据（oldPassword, newPassword）
        current_user: 当前认证用户（从JWT中提取）
        db: 数据库会话
        
    Returns:
        dict: 包含成功消息的响应
        
    Raises:
        HTTPException: 401 如果旧密码错误
    """
    try:
        await UserService.change_password(
            db, 
            current_user.id, 
            data.oldPassword, 
            data.newPassword
        )
        
        return {
            "code": 200,
            "data": None,
            "message": "密码修改成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "data": None,
                "message": str(e),
                "error": "CHANGE_PASSWORD_FAILED"
            }
        )


@router.post(
    "/forgot-password",
    response_model=Dict,
    summary="忘记密码",
    description="""
    忘记密码，生成密码重置令牌。
    
    出于安全考虑，无论邮箱是否存在，都会返回成功消息。
    实际重置链接会通过邮件发送给用户。
    
    请求体必须包含：
    - email: 注册邮箱
    
    错误响应：
    - 422: 请求参数验证失败
    """
)
async def forgot_password(
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """忘记密码（生成重置令牌）
    
    Security: Always returns success to prevent user enumeration
    
    Args:
        data: 忘记密码数据（email）
        db: 数据库会话
        
    Returns:
        dict: 包含成功消息的响应
    """
    try:
        await UserService.forgot_password(db, data.email)
        
        return {
            "code": 200,
            "data": None,
            "message": "重置密码邮件已发送",
            "error": None
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "data": None,
                "message": str(e),
                "error": "FORGOT_PASSWORD_FAILED"
            }
        )


@router.post(
    "/reset-password",
    response_model=Dict,
    summary="重置密码",
    description="""
    使用重置令牌重置密码。
    
    请求体必须包含：
    - email: 注册邮箱
    - token: 重置令牌（从邮件中获取）
    - newPassword: 新密码（6-50字符）
    
    错误响应：
    - 400: 重置链接无效或已过期
    - 404: 用户不存在
    - 422: 请求参数验证失败
    """
)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """重置密码
    
    Args:
        data: 重置密码数据（email, token, newPassword）
        db: 数据库会话
        
    Returns:
        dict: 包含成功消息的响应
        
    Raises:
        HTTPException: 400 如果重置链接无效或已过期
    """
    try:
        await UserService.reset_password(
            db, 
            data.email, 
            data.token, 
            data.newPassword
        )
        
        return {
            "code": 200,
            "data": None,
            "message": "密码重置成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": 400,
                "data": None,
                "message": str(e),
                "error": "RESET_PASSWORD_FAILED"
            }
        )
