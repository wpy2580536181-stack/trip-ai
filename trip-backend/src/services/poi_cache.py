"""POI 缓存层 — Redis 缓存景点检索结果。

热点城市（top-20）的景点/美食检索结果缓存 1 小时，
避免每次请求都走完整的 Chroma 向量检索 + MySQL 全文搜索链路。

预期收益：缓存命中时 research 阶段从 ~17-18s → ~1-3ms。
"""

import hashlib
import json
import logging
import time
from typing import Optional

from src.config.redis_client import get_redis, is_redis_available

logger = logging.getLogger(__name__)

# 缓存配置
POI_CACHE_PREFIX = "poi:"
POI_CACHE_TTL_S = 3600  # 1 小时
POI_CACHE_MAX_SIZE_MEMORY = 500  # 内存降级模式最大条目数

# 热点城市列表（启动时可预热）
HOT_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "西安", "重庆", "南京",
    "天津", "长沙", "苏州", "厦门", "青岛", "大连", "昆明", "三亚", "哈尔滨", "桂林",
]

# 类别列表
CATEGORIES = ["attraction", "food"]


# ---------------------------------------------------------------------------
# Memory fallback backend
# ---------------------------------------------------------------------------

class _MemoryPOICache:
    """进程内内存缓存（Redis 不可用时降级）。"""

    def __init__(self, max_size: int = POI_CACHE_MAX_SIZE_MEMORY):
        self._max_size = max_size
        self._store: dict = {}  # key -> (value_json, created_at)

    async def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, created_at = entry
        if time.time() - created_at > POI_CACHE_TTL_S:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str) -> None:
        if len(self._store) >= self._max_size:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[key] = (value, time.time())

    async def delete_pattern(self, city: str) -> int:
        """删除指定城市的所有缓存条目。"""
        prefix = f"{POI_CACHE_PREFIX}{city}:"
        keys_to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._store[k]
        return len(keys_to_delete)


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class _RedisPOICache:
    """Redis 后端 POI 缓存。"""

    async def get(self, key: str) -> Optional[str]:
        r = get_redis()
        if r is None:
            return None
        try:
            return await r.get(key)
        except Exception as e:
            logger.debug("Redis POI cache get failed: %s", e)
            return None

    async def set(self, key: str, value: str) -> None:
        r = get_redis()
        if r is None:
            return
        try:
            await r.setex(key, POI_CACHE_TTL_S, value)
        except Exception as e:
            logger.debug("Redis POI cache set failed: %s", e)

    async def delete_pattern(self, city: str) -> int:
        """删除指定城市的所有缓存条目（SCAN + DEL）。"""
        r = get_redis()
        if r is None:
            return 0
        pattern = f"{POI_CACHE_PREFIX}{city}:*"
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
            logger.warning("Redis POI cache delete_pattern failed: %s", e)
        return deleted


# ---------------------------------------------------------------------------
# POI Cache API
# ---------------------------------------------------------------------------

class POICache:
    """POI 缓存统一接口。

    优先使用 Redis，Redis 不可用时降级为内存模式。
    """

    def __init__(self):
        use_redis = is_redis_available()
        self._backend = _RedisPOICache() if use_redis else _MemoryPOICache()
        self._backend_type = "redis" if use_redis else "memory"
        logger.info("POI cache backend: %s", self._backend_type)

    @staticmethod
    def _build_key(city: str, category: str, query: str) -> str:
        """构建缓存 key：poi:{city}:{category}:{query_hash}"""
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        return f"{POI_CACHE_PREFIX}{city}:{category}:{query_hash}"

    def _normalize_query(self, city: str, category: str, query: str) -> str:
        """标准化查询字符串，用于缓存 key 构建。"""
        # 去掉 query 中重复的城市名
        normalized = query.replace(city, "").strip()
        if not normalized:
            normalized = category
        return normalized

    async def get(self, city: str, category: str, query: str) -> Optional[str]:
        """查询 POI 缓存。

        Args:
            city: 城市名
            category: 类别（attraction/food）
            query: 搜索关键词

        Returns:
            缓存的 JSON 字符串，未命中返回 None
        """
        normalized = self._normalize_query(city, category, query)
        key = self._build_key(city, category, normalized)
        cached = await self._backend.get(key)
        if cached is not None:
            logger.info("poi_cache|hit city=%s category=%s", city, category)
            return cached
        logger.debug("poi_cache|miss city=%s category=%s", city, category)
        return None

    async def set(self, city: str, category: str, query: str, result: str) -> None:
        """写入 POI 缓存。

        Args:
            city: 城市名
            category: 类别
            query: 搜索关键词
            result: 检索结果 JSON 字符串
        """
        normalized = self._normalize_query(city, category, query)
        key = self._build_key(city, category, normalized)
        await self._backend.set(key, result)

    async def warm_city(self, city: str) -> int:
        """预热单个城市（void — 仅标记 key，实际数据在首次检索时缓存）。

        Returns:
            0（预热不实际加载数据，只是标记）
        """
        logger.info("poi_cache|warm city=%s", city)
        return 0

    async def invalidate_city(self, city: str) -> int:
        """失效指定城市的全部缓存（数据更新后调用）。"""
        return await self._backend.delete_pattern(city)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_poi_cache: Optional[POICache] = None


def get_poi_cache() -> POICache:
    """获取全局 POICache 单例。"""
    global _poi_cache
    if _poi_cache is None:
        _poi_cache = POICache()
    return _poi_cache
