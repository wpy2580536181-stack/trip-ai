"""LLM Cache — LLM 响应缓存。

基于 prompt 内容 hash（相同 prompt 返回缓存结果）。
Redis + 内存双模式，无 Redis 时降级为内存 dict。
可选开关（settings.llm_cache_enabled）。
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from src.config.redis_client import get_redis, is_redis_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_prompt(prompt: str) -> str:
    """对 prompt 内容做 SHA-256 hash。"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Memory backend (fallback)
# ---------------------------------------------------------------------------

class _MemoryLLMCache:
    """进程内内存缓存。"""

    def __init__(self, max_size: int = 200, ttl_s: int = 600):
        self._max_size = max_size
        self._ttl_s = ttl_s
        self._store: Dict[str, Tuple[str, float]] = {}  # key -> (value, created_at)

    async def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, created_at = entry
        if time.time() - created_at > self._ttl_s:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        if len(self._store) >= self._max_size:
            # 淘汰最旧
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        self._store[key] = (value, time.time())


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class _RedisLLMCache:
    """Redis 后端。"""

    def __init__(self, ttl_s: int = 600):
        self._prefix = "llm_cache:"
        self._ttl_s = ttl_s

    async def get(self, key: str) -> Optional[str]:
        r = get_redis()
        if r is None:
            return None
        try:
            return await r.get(self._prefix + key)
        except Exception as e:
            logger.debug("Redis LLM cache get failed: %s", e)
            return None

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        r = get_redis()
        if r is None:
            return
        try:
            await r.setex(self._prefix + key, ttl_s, value)
        except Exception as e:
            logger.debug("Redis LLM cache set failed: %s", e)


# ---------------------------------------------------------------------------
# LLMCache
# ---------------------------------------------------------------------------

class LLMCache:
    """LLM 响应缓存。

    相同 prompt（SHA-256 hash）→ 返回缓存结果，避免重复调用 LLM。

    backend: "auto" | "redis" | "memory"
    ttl_s: 缓存过期时间（秒）
    max_size: 内存模式最大条目数
    """

    def __init__(
        self,
        backend: str = "auto",
        ttl_s: int = 600,
        max_size: int = 200,
    ):
        self._ttl_s = ttl_s
        self._backend_mode = backend
        self._cache = self._make_backend(backend, ttl_s, max_size)

    def _make_backend(self, backend: str, ttl_s: int, max_size: int):
        use_redis = (
            backend == "redis"
            or (backend == "auto" and is_redis_available())
        )
        if use_redis:
            return _RedisLLMCache(ttl_s)
        return _MemoryLLMCache(max_size, ttl_s)

    async def get(self, prompt: str) -> Optional[str]:
        """查询缓存的 LLM 响应。

        Args:
            prompt: LLM prompt 文本

        Returns:
            缓存的响应文本，未命中返回 None
        """
        key = _hash_prompt(prompt)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.info("LLM cache hit key=%s", key)
            return cached
        return None

    async def set(self, prompt: str, response: str, ttl_s: Optional[int] = None) -> None:
        """写入 LLM 响应缓存。

        Args:
            prompt: LLM prompt 文本
            response: LLM 响应文本
            ttl_s: TTL（可选，覆盖默认值）
        """
        key = _hash_prompt(prompt)
        await self._cache.set(key, response, ttl_s or self._ttl_s)
        logger.info("LLM cache set key=%s ttl=%d", key, ttl_s or self._ttl_s)

    async def get_or_compute(
        self,
        prompt: str,
        compute,
        ttl_s: Optional[int] = None,
    ) -> Tuple[str, bool]:
        """查询缓存或执行 compute 并写入缓存。

        Args:
            prompt: LLM prompt 文本
            compute: 缓存未命中时执行的异步 callable（无参数）
            ttl_s: TTL（可选）

        Returns:
            (response, hit) — hit 表示是否缓存命中
        """
        cached = await self.get(prompt)
        if cached is not None:
            return cached, True

        response = await compute()
        await self.set(prompt, response, ttl_s)
        return response, False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_llm_cache: Optional[LLMCache] = None


def get_llm_cache() -> Optional[LLMCache]:
    """获取全局 LLMCache 实例（如果启用）。

    返回 None 表示 LLM cache 未启用。
    """
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache

    try:
        from src.config.settings import settings
        if not getattr(settings, "llm_cache_enabled", False):
            return None
        _llm_cache = LLMCache(
            backend="auto",
            ttl_s=getattr(settings, "llm_cache_ttl_s", 600),
            max_size=getattr(settings, "llm_cache_max_size", 200),
        )
        return _llm_cache
    except Exception as e:
        logger.warning("LLM cache 初始化失败: %s", e)
        return None
