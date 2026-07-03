"""Script to generate auth.py with correct syntax"""
import textwrap

content = textwrap.dedent("""
"""JWT Authentication utilities for FastAPI"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config.settings import settings
from src.config.database import async_session
from src.models.user import User
from src.models.role import Role


# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_current_user(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    \"\"\"FastAPI dependency: Get current authenticated user from JWT\"\"\"
    
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "Authentication required", "error": "UNAUTHORIZED"}
        )
    
    token = credentials.credentials
    
    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        
        user_id = payload.get("userId")
        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail={"code": 401, "message": "Invalid token", "error": "UNAUTHORIZED"}
            )
        
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "Invalid or expired token", "error": "UNAUTHORIZED"}
        )
    
    # Get user from database
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            raise HTTPException(
                status_code=401,
                detail={"code": 401, "message": "User not found", "error": "UNAUTHORIZED"}
            )
        
        # Store user in request state for access in endpoints
        if request:
            request.state.user = user
        
        return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User | None:
    \"\"\"Optional authentication - returns None if not authenticated\"\"\"
    
    try:
        return await get_current_user(None, credentials)
    except HTTPException:
        return None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    \"\"\"FastAPI dependency: Require admin role\"\"\"
    
    if current_user.role_id != 1:  # 1 = ADMIN role
        raise HTTPException(
            status_code=403,
            detail={"code": 403, "message": "Admin access required", "error": "FORBIDDEN"}
        )
    
    return current_user
""").strip()

with open("/Users/wang/Documents/trip/trip-server-py/src/middleware/auth.py", "w") as f:
    f.write(content)

print("auth.py generated successfully")
