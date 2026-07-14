"""Security utilities (password hashing + JWT)"""

import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from src.config.settings import settings
from src.exceptions import UnauthorizedException


def hash_password(password: str) -> str:
    """Hash password with bcrypt (compatible with Node.js bcryptjs)"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash (compatible with Node.js bcryptjs)"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_access_token(user_id: int, username: str, role_id: int) -> str:
    """Create JWT access token (compatible with Node.js version)"""
    payload = {
        "userId": user_id,
        "username": username,
        "roleId": role_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expires_in_days)
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Dict:
    """Decode JWT token
    
    Returns:
        dict: JWT payload
        
    Raises:
        UnauthorizedException: if token is expired or invalid
    """
    try:
        payload = jwt.decode(
            token, 
            settings.jwt_secret, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException("Token expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedException("Invalid token")


def generate_token(user_id: int, username: str, role_id: int) -> str:
    """Alias for create_access_token (for compatibility with Node.js naming)"""
    return create_access_token(user_id, username, role_id)
