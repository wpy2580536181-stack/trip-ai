"""Tests for security utilities (password hashing + JWT)"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone

from src.config.settings import settings
from src.exceptions import UnauthorizedException
from src.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


class TestPasswordHashing:
    """Test cases for password hashing"""

    def test_hash_password_not_plaintext(self):
        """哈希结果不等于原文"""
        password = "MySecret@123"
        hashed = hash_password(password)
        assert hashed != password

    def test_hash_password_unique(self):
        """相同密码两次哈希不同（bcrypt salt）"""
        password = "MySecret@123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """正确密码验证通过"""
        password = "MySecret@123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_wrong(self):
        """错误密码验证失败"""
        hashed = hash_password("CorrectPassword@123")
        assert verify_password("WrongPassword@123", hashed) is False

    def test_verify_password_empty(self):
        """空密码处理：空字符串哈希后可验证"""
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


class TestJWTTokens:
    """Test cases for JWT token creation and decoding"""

    def test_create_access_token_contains_user_id(self):
        """token 包含 user_id（以 userId 键存储）"""
        token = create_access_token(user_id=42, username="alice", role_id=2)
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        assert payload["userId"] == 42
        assert payload["username"] == "alice"
        assert payload["roleId"] == 2

    def test_decode_access_token_roundtrip(self):
        """create → decode 往返一致"""
        token = create_access_token(user_id=7, username="bob", role_id=1)
        payload = decode_token(token)
        assert payload["userId"] == 7
        assert payload["username"] == "bob"
        assert payload["roleId"] == 1

    def test_decode_access_token_expired(self):
        """过期 token 抛 UnauthorizedException"""
        # Manually create an already-expired token
        expired_payload = {
            "userId": 1,
            "username": "expired_user",
            "roleId": 2,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(UnauthorizedException, match="expired"):
            decode_token(expired_token)

    def test_decode_access_token_tampered(self):
        """篡改 token 抛 UnauthorizedException"""
        token = create_access_token(user_id=1, username="alice", role_id=2)
        # Tamper by modifying the payload (middle part) to change userId
        parts = token.split(".")
        # Replace payload with a different one (signed with wrong secret)
        bad_payload = jwt.encode(
            {"userId": 999, "username": "evil", "roleId": 1},
            "wrong-secret",
            algorithm=settings.jwt_algorithm,
        )
        tampered_token = bad_payload
        with pytest.raises(UnauthorizedException):
            decode_token(tampered_token)

    def test_create_token_with_expiry(self):
        """带过期时间的 token（默认 7 天）"""
        token = create_access_token(user_id=10, username="charlie", role_id=2)
        payload = decode_token(token)
        # exp should be approximately 7 days from now
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = exp - now
        # Should be roughly 7 days (allow 1 minute tolerance)
        assert 6 * 24 * 3600 < delta.total_seconds() < 8 * 24 * 3600

    def test_create_token_without_expiry(self):
        """无过期时间手动构建的 token 也可 decode"""
        # Build a token without exp to verify decode handles it
        payload = {
            "userId": 99,
            "username": "noexpiry",
            "roleId": 2,
        }
        token = jwt.encode(
            payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        decoded = decode_token(token)
        assert decoded["userId"] == 99
        assert "exp" not in decoded
