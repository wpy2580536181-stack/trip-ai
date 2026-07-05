"""Tests for utility functions (tokens + serialization)"""

import os
import pytest

from src.utils.tokens import (
    estimate_tokens,
    estimate_messages_tokens,
    get_history_max_tokens,
    DEFAULT_HISTORY_MAX_TOKENS,
)
from src.utils.serialization import to_camel, serialize_to_camel


class TestEstimateTokens:
    """Test cases for estimate_tokens"""

    def test_estimate_tokens_chinese(self):
        """纯中文 '你好世界' (4 CJK chars) ≈ ceil(4/1.5) = 3 tokens"""
        result = estimate_tokens("你好世界")
        assert result == 3  # ceil(4 / 1.5) = 3

    def test_estimate_tokens_english(self):
        """纯英文 'hello world' (11 chars) ≈ ceil(11/4) = 3 tokens"""
        result = estimate_tokens("hello world")
        assert result == 3  # ceil(11 / 4) = 3

    def test_estimate_tokens_mixed(self):
        """中英文混合：'你好world' → 2 CJK + 5 other → ceil(2/1.5 + 5/4) = ceil(1.33+1.25) = ceil(2.58) = 3"""
        result = estimate_tokens("你好world")
        assert result == 3

    def test_estimate_tokens_empty(self):
        """空字符串 → 0"""
        assert estimate_tokens("") == 0


class TestEstimateMessagesTokens:
    """Test cases for estimate_messages_tokens"""

    def test_estimate_messages_tokens(self):
        """消息列表总 token"""
        messages = [
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "你好世界"},
        ]
        total = estimate_messages_tokens(messages)
        # "hello world" = 3, "你好世界" = 3
        assert total == 6

    def test_estimate_messages_tokens_empty(self):
        """空列表 → 0"""
        assert estimate_messages_tokens([]) == 0


class TestGetHistoryMaxTokens:
    """Test cases for get_history_max_tokens"""

    def test_get_history_max_tokens_default(self):
        """默认值等于 DEFAULT_HISTORY_MAX_TOKENS"""
        # Ensure env var is not set
        os.environ.pop("HISTORY_MAX_TOKENS", None)
        assert get_history_max_tokens() == DEFAULT_HISTORY_MAX_TOKENS

    def test_get_history_max_tokens_env_override(self):
        """环境变量覆盖"""
        os.environ["HISTORY_MAX_TOKENS"] = "8000"
        try:
            assert get_history_max_tokens() == 8000
        finally:
            os.environ.pop("HISTORY_MAX_TOKENS", None)


class TestToCamel:
    """Test cases for to_camel"""

    def test_to_camel_snake_case(self):
        """user_id → userId"""
        assert to_camel("user_id") == "userId"

    def test_to_camel_already_camel(self):
        """userId 不变（无下划线，原样返回）"""
        assert to_camel("userId") == "userId"

    def test_to_camel_multi_word(self):
        """created_at → createdAt"""
        assert to_camel("created_at") == "createdAt"


class TestSerializeToCamel:
    """Test cases for serialize_to_camel"""

    def test_serialize_to_camel_dict(self):
        """整个 dict 转换"""
        data = {"user_id": 1, "created_at": "2024-01-01"}
        result = serialize_to_camel(data)
        assert result == {"userId": 1, "createdAt": "2024-01-01"}

    def test_serialize_to_camel_nested(self):
        """嵌套 dict/list 转换"""
        data = {
            "user_id": 1,
            "user_profile": {
                "first_name": "Alice",
                "last_name": "Smith",
            },
            "user_tags": [
                {"tag_name": "admin"},
                {"tag_name": "user"},
            ],
        }
        result = serialize_to_camel(data)
        assert result["userId"] == 1
        assert result["userProfile"] == {"firstName": "Alice", "lastName": "Smith"}
        assert result["userTags"] == [{"tagName": "admin"}, {"tagName": "user"}]
