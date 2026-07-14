"""User schemas (request/response)"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from datetime import datetime
from typing import Optional


class UserRegister(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=50, description="密码")


class UserLogin(BaseModel):
    """登录请求（支持用户名或邮箱）"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户响应（不含密码）"""
    model_config = ConfigDict(
        serialize_by_alias=True,
        from_attributes=True
    )
    
    id: int
    username: str
    email: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    role_id: int = Field(alias="roleId")
    status: int = 1
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class LoginResponse(BaseModel):
    """登录响应（含 JWT）"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    id: int
    username: str
    email: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    role_id: int = Field(alias="roleId")
    token: str


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    old_password: str = Field(..., alias="oldPassword", description="旧密码")
    new_password: str = Field(..., alias="newPassword", min_length=6, max_length=50, description="新密码")


class ForgotPasswordRequest(BaseModel):
    """忘记密码请求"""
    email: EmailStr = Field(..., description="注册邮箱")


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    email: EmailStr = Field(..., description="注册邮箱")
    token: str = Field(..., description="重置令牌")
    new_password: str = Field(..., alias="newPassword", min_length=6, max_length=50, description="新密码")


class UserUpdateRequest(BaseModel):
    """更新用户信息请求"""
    nickname: Optional[str] = Field(None, max_length=100, description="昵称")
    avatar: Optional[str] = Field(None, description="头像URL")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    bio: Optional[str] = Field(None, description="个人简介")
    preferences: Optional[dict] = Field(None, description="偏好设置")


class FeedbackCreate(BaseModel):
    """提交反馈请求"""
    message_id: int = Field(..., alias="messageId", description="消息ID")
    conversation_id: int = Field(..., alias="conversationId", description="对话ID")
    rating: int = Field(..., description="评分（1=点赞，-1=点踩）")
    comment: Optional[str] = Field(None, description="评论")
    tags: Optional[list[str]] = Field(None, description="标签")


class FeedbackResponse(BaseModel):
    """反馈响应"""
    id: int
    rating: int
