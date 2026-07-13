"""Research Bundle 全量缓存。

在 research_node 入口处缓存整包工具调用结果（景点、美食、酒店、天气、距离），
避免每次请求都调度 5 个并行工具。即使 POI 缓存已命中，仍可跳过工具编排和事件发送开销。

Cache key: research_bundle:{city}:{budget_tier}:{days}:{departure_city}:{interests_hash}
TTL: 300s (5 分钟，天气时效性有限)
优先 Redis，降级内存模式。
"""

import hashlib
import json
import logging
import time
from typing import Any, Optional

from src.config.redis_client import get_redis, is_redis_available

logger = logging.getLogger(__name__)

# 缓存配置
BUNDLE_CACHE_PREFIX = "research_bundle:"
BUNDLE_CACHE_TTL_S = 300  # 5 分钟
BUNDLE_CACHE_MAX_SIZE_MEMORY = 200  # 内存降级模式最大条目数


# ---------------------------------------------------------------------------
# Memory fallback backend
# ---------------------------------------------------------------------------

class _MemoryBundleCache:
    """进程内内存缓存（Redis 不可用时降级）。"""

    def __init__(self, max_size: int = BUNDLE_CACHE_MAX_SIZE_MEMORY):
        self._max_size = max_size
        self._store: dict = {}

    async def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value_json, created_at = entry
        if time.time() - created_at > BUNDLE_CACHE_TTL_S:
            del self._store[key]
            return None
        return value_json

    async def set(self, key: str, value_json: str) -> None:
        if len(self._store) >= self._max_size:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[key] = (value_json, time.time())

    async def invalidate_city(self, city: str) -> int:
        prefix = f"{BUNDLE_CACHE_PREFIX}{city}:"
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class _RedisBundleCache:
    """Redis 后端。"""

    async def get(self, key: str) -> Optional[str]:
        r = get_redis()
        if r is None:
            return None
        try:
            return await r.get(key)
        except Exception as e:
            logger.debug("Redis bundle cache get failed: %s", e)
            return None

    async def set(self, key: str, value_json: str) -> None:
        r = get_redis()
        if r is None:
            return
        try:
            await r.setex(key, BUNDLE_CACHE_TTL_S, value_json)
        except Exception as e:
            logger.debug("Redis bundle cache set failed: %s", e)

    async def invalidate_city(self, city: str) -> int:
        r = get_redis()
        if r is None:
            return 0
        pattern = f"{BUNDLE_CACHE_PREFIX}{city}:*"
        deleted = 0
        try:
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match=pattern, count=100)
                if keys:
                    await r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Redis bundle cache invalidate failed: %s", e)
        return deleted


# ---------------------------------------------------------------------------
# ResearchBundleCache API
# ---------------------------------------------------------------------------

class ResearchBundleCache:
    """ResearchBundle 缓存统一接口。

    优先 Redis，不可用时降级为内存模式。
    """

    def __init__(self):
        use_redis = is_redis_available()
        self._backend = _RedisBundleCache() if use_redis else _MemoryBundleCache()
        self._backend_type = "redis" if use_redis else "memory"
        logger.info("ResearchBundle cache backend: %s", self._backend_type)

    @staticmethod
    def _build_key(
        city: str,
        budget_tier: str,
        days: int,
        departure_city: Optional[str],
        interests_hash: str,
    ) -> str:
        """构建缓存 key。"""
        dep = departure_city or "none"
        return f"{BUNDLE_CACHE_PREFIX}{city}:{budget_tier}:{days}d:{dep}:{interests_hash}"

    @staticmethod
    def _compute_budget_tier(budget: Optional[int]) -> str:
        """将预算映射到档位，使相同档位的请求可共享缓存。"""
        if budget is None:
            return "unknown"
        if budget < 1000:
            return "low"
        elif budget < 3000:
            return "medium"
        elif budget < 8000:
            return "high"
        else:
            return "luxury"

    @staticmethod
    def _compute_interests_hash(user_preferences: Optional[dict]) -> str:
        """计算兴趣标签的 hash。"""
        if not user_preferences or not isinstance(user_preferences, dict):
            return "none"
        interests = user_preferences.get("interests", [])
        if not interests:
            return "none"
        raw = "".join(sorted(str(i) for i in interests))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]

    async def get(
        self,
        city: str,
        budget: Optional[int],
        days: int,
        departure_city: Optional[str],
        user_preferences: Optional[dict],
    ) -> Optional[dict]:
        """查询 ResearchBundle 缓存。

        Returns:
            缓存的 dict 形式的 ResearchBundle，未命中返回 None
        """
        budget_tier = self._compute_budget_tier(budget)
        interests_hash = self._compute_interests_hash(user_preferences)
        key = self._build_key(city, budget_tier, days, departure_city, interests_hash)

        cached = await self._backend.get(key)
        if cached is not None:
            logger.info(
                "bundle_cache|hit city=%s budget_tier=%s days=%d",
                city, budget_tier, days,
            )
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                logger.warning("bundle_cache|json_decode_error city=%s", city)
                return None

        logger.debug(
            "bundle_cache|miss city=%s budget_tier=%s days=%d",
            city, budget_tier, days,
        )
        return None

    async def set(
        self,
        city: str,
        budget: Optional[int],
        days: int,
        departure_city: Optional[str],
        user_preferences: Optional[dict],
        bundle: dict,
    ) -> None:
        """写入 ResearchBundle 缓存。"""
        budget_tier = self._compute_budget_tier(budget)
        interests_hash = self._compute_interests_hash(user_preferences)
        key = self._build_key(city, budget_tier, days, departure_city, interests_hash)

        try:
            # 确保 bundle 中的值都是 JSON 可序列化的字符串
            clean_bundle = {
                k: str(v) if not isinstance(v, str) else v
                for k, v in bundle.items()
            }
            value_json = json.dumps(clean_bundle, ensure_ascii=False)
            await self._backend.set(key, value_json)
        except Exception as e:
            logger.warning("bundle_cache|set_failed city=%s err=%s", city, e)

    async def invalidate_city(self, city: str) -> int:
        """清除指定城市的所有缓存。"""
        return await self._backend.invalidate_city(city)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bundle_cache: Optional[ResearchBundleCache] = None


def get_bundle_cache() -> ResearchBundleCache:
    """获取全局 ResearchBundleCache 单例。"""
    global _bundle_cache
    if _bundle_cache is None:
        _bundle_cache = ResearchBundleCache()
    return _bundle_cache
