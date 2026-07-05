"""ToolCache — Agent 工具结果缓存。

迁移自 Node.js trip-server/src/services/llmGuard/toolCache.ts。

支持两种归一化路径（per-tool 独立配置）：
- 字面归一化（默认）：trim + lowercase + sort keys
- embedding 归一化：算 query embedding，遍历 cache 找 cosine sim ≥ threshold 的 entry

后端：
- Redis（优先，使用已有的 redis_client）
- 内存 dict（无 Redis 时降级）
"""

import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Dict, List, Optional, Tuple

from src.config.redis_client import get_redis, is_redis_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingKeyConfig:
    """embedding 归一化配置。"""

    extractor: Callable[[dict], str]
    threshold: float = 0.85
    embedder: Optional[Callable[[str], Awaitable[List[float]]]] = None


@dataclass
class ToolCacheConfig:
    """单个 tool 的缓存配置。"""

    ttl_s: int = 300  # 缓存 TTL（秒）
    max_size: int = 100  # 最大条目数
    embedding_key: Optional[EmbeddingKeyConfig] = None


@dataclass
class _ToolEntry:
    """缓存条目。"""

    value: str
    literal_key: str
    vector: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dot_product(a: List[float], b: List[float]) -> float:
    """点积（cosine 相似度，前提：两向量已 L2 normalize）。"""
    return sum(x * y for x, y in zip(a, b))


def _normalize_city(name: str) -> str:
    """城市名归一化：去空格、统一小写。

    可扩展：拼音转换等。
    """
    return name.strip().lower()


def _make_literal_key(tool_name: str, args: dict) -> str:
    """构建字面缓存 key。

    - 排序 object keys（让 {a, b} == {b, a}）
    - string 字段 trim + lower
    - 跳过 None 字段
    """
    normalized = {}
    for k in sorted(args.keys()):
        v = args[k]
        if v is None:
            continue
        if isinstance(v, str):
            # 城市名特殊归一化
            if k in ("city", "from_city", "to_city"):
                v = _normalize_city(v)
            else:
                v = v.strip().lower()
        normalized[k] = v
    return f"{tool_name}:{json.dumps(normalized, ensure_ascii=False, sort_keys=True)}"


# ---------------------------------------------------------------------------
# Memory backend (fallback)
# ---------------------------------------------------------------------------

class _MemoryBackend:
    """进程内内存缓存（LRU-like 淘汰）。"""

    def __init__(self, max_size: int, ttl_s: int):
        self._max_size = max_size
        self._ttl_s = ttl_s
        self._store: Dict[str, _ToolEntry] = {}

    async def get(self, key: str) -> Optional[_ToolEntry]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry.created_at > self._ttl_s:
            del self._store[key]
            return None
        return entry

    async def set(self, key: str, entry: _ToolEntry, ttl_s: int) -> None:
        # 淘汰：超 max_size 时删除最旧的
        if len(self._store) >= self._max_size:
            oldest_key = min(self._store, key=lambda k: self._store[k].created_at)
            del self._store[oldest_key]
        self._store[key] = entry

    async def values(self) -> List[_ToolEntry]:
        now = time.time()
        # 清理过期
        expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl_s]
        for k in expired:
            del self._store[k]
        return list(self._store.values())


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class _RedisBackend:
    """Redis 后端（per-tool 使用独立 hash key prefix）。"""

    def __init__(self, tool_name: str, max_size: int, ttl_s: int):
        self._prefix = f"tool_cache:{tool_name}:"
        self._index_key = f"tool_cache_idx:{tool_name}"
        self._max_size = max_size
        self._ttl_s = ttl_s

    async def get(self, key: str) -> Optional[_ToolEntry]:
        r = get_redis()
        if r is None:
            return None
        try:
            raw = await r.get(self._prefix + key)
            if raw is None:
                return None
            data = json.loads(raw)
            return _ToolEntry(
                value=data["v"],
                literal_key=data["lk"],
                vector=data.get("vec"),
                created_at=data.get("ts", time.time()),
            )
        except Exception as e:
            logger.debug("Redis get failed: %s", e)
            return None

    async def set(self, key: str, entry: _ToolEntry, ttl_s: int) -> None:
        r = get_redis()
        if r is None:
            return
        try:
            data = json.dumps({
                "v": entry.value,
                "lk": entry.literal_key,
                "vec": entry.vector,
                "ts": entry.created_at,
            }, ensure_ascii=False)
            redis_key = self._prefix + key
            await r.setex(redis_key, ttl_s, data)
            # 维护 index set（用于 values()）
            await r.sadd(self._index_key, key)
            await r.expire(self._index_key, ttl_s * 2)
        except Exception as e:
            logger.debug("Redis set failed: %s", e)

    async def values(self) -> List[_ToolEntry]:
        r = get_redis()
        if r is None:
            return []
        try:
            keys = await r.smembers(self._index_key)
            entries = []
            for k in keys:
                entry = await self.get(k)
                if entry:
                    entries.append(entry)
            return entries
        except Exception as e:
            logger.debug("Redis values failed: %s", e)
            return []


# ---------------------------------------------------------------------------
# ToolCache
# ---------------------------------------------------------------------------

class ToolCache:
    """按 tool 维度隔离的缓存管理器。

    支持两种归一化路径（per-tool 独立）：
    - 字面归一化（默认）：trim + lowercase + sort keys
    - embedding 归一化：算 query embedding，遍历 cache 找 cosine sim ≥ threshold 的 entry

    cache_backend: "auto" | "redis" | "memory"
        auto = 有 Redis 用 Redis，否则内存
    """

    def __init__(
        self,
        configs: Dict[str, ToolCacheConfig],
        backend: str = "auto",
    ):
        self._configs = configs
        self._backend_mode = backend
        self._caches: Dict[str, Any] = {}

        for tool_name, cfg in configs.items():
            self._caches[tool_name] = self._make_backend(tool_name, cfg)

    def _make_backend(self, tool_name: str, cfg: ToolCacheConfig):
        use_redis = (
            self._backend_mode == "redis"
            or (self._backend_mode == "auto" and is_redis_available())
        )
        if use_redis:
            return _RedisBackend(tool_name, cfg.max_size, cfg.ttl_s)
        return _MemoryBackend(cfg.max_size, cfg.ttl_s)

    async def get_or_compute(
        self,
        tool_name: str,
        args: dict,
        compute: Callable[[], Awaitable[str]],
    ) -> Tuple[str, bool]:
        """查询缓存或执行 compute 并写入缓存。

        Args:
            tool_name: 工具名称
            args: 工具参数
            compute: 缓存未命中时执行的异步函数

        Returns:
            (result, hit) — hit 表示是否缓存命中
        """
        cfg = self._configs.get(tool_name)
        cache = self._caches.get(tool_name)
        if cfg is None or cache is None:
            result = await compute()
            return result, False

        if cfg.embedding_key is not None:
            return await self._embedding_lookup(tool_name, args, compute, cache, cfg)
        return await self._literal_lookup(tool_name, args, compute, cache, cfg)

    # -- internal --

    async def _literal_lookup(
        self,
        tool_name: str,
        args: dict,
        compute: Callable[[], Awaitable[str]],
        cache: Any,
        cfg: ToolCacheConfig,
    ) -> Tuple[str, bool]:
        literal_key = _make_literal_key(tool_name, args)
        cached = await cache.get(literal_key)
        if cached is not None:
            logger.info("tool cache hit tool=%s mode=literal key=%s", tool_name, literal_key)
            return cached.value, True

        result = await compute()
        entry = _ToolEntry(value=result, literal_key=literal_key, vector=None)
        await cache.set(literal_key, entry, cfg.ttl_s)
        logger.info("tool cache miss tool=%s mode=literal key=%s", tool_name, literal_key)
        return result, False

    async def _embedding_lookup(
        self,
        tool_name: str,
        args: dict,
        compute: Callable[[], Awaitable[str]],
        cache: Any,
        cfg: ToolCacheConfig,
    ) -> Tuple[str, bool]:
        ek = cfg.embedding_key
        assert ek is not None
        threshold = ek.threshold
        key_text = ek.extractor(args)

        # 获取 embedding
        embedder = ek.embedder
        if embedder is None:
            try:
                from src.services.rag.embeddings import embed_query_async
                embedder = embed_query_async
            except ImportError:
                logger.warning("embedding 模块不可用，降级到字面查找")
                return await self._literal_lookup(tool_name, args, compute, cache, cfg)

        try:
            query_vec = await embedder(key_text)
        except Exception as e:
            logger.warning("embedding 调用失败，降级到字面查找: %s", e)
            return await self._literal_lookup(tool_name, args, compute, cache, cfg)

        # 遍历缓存找最相似的
        best_sim = -1.0
        best_entry: Optional[_ToolEntry] = None
        for entry in await cache.values():
            if entry.vector is None:
                continue
            sim = _dot_product(query_vec, entry.vector)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= threshold:
            logger.info(
                "tool cache hit tool=%s mode=embedding sim=%.3f threshold=%.2f",
                tool_name, best_sim, threshold,
            )
            return best_entry.value, True

        result = await compute()
        entry_key = f"embed:{key_text}"
        entry = _ToolEntry(value=result, literal_key=entry_key, vector=query_vec)
        await cache.set(entry_key, entry, cfg.ttl_s)
        logger.info(
            "tool cache miss tool=%s mode=embedding best_sim=%.3f key=%s",
            tool_name, best_sim if best_sim > 0 else 0, key_text,
        )
        return result, False


# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------

def with_tool_cache(
    tool: Any,
    tool_cache: "ToolCache",
    tool_name: str,
) -> Any:
    """给 LangChain 工具加缓存层。**必须套在 with_resilience 外面**：

    withToolCache → withResilience → 原始 tool

    顺序原因：
    - 缓存命中时直接返回，跳过整个 withResilience（包括重试和 fallback）
    - 缓存未命中时走 withResilience 正常流程（重试 + fallback）
    """
    original_arun = tool._arun if hasattr(tool, "_arun") else None
    if original_arun is None:
        return tool

    async def cached_arun(*args: Any, **kwargs: Any) -> Any:
        # 从 args/kwargs 提取工具参数用于缓存 key
        # LangChain 工具第一个参数通常是 input dict 或关键字参数
        if args and isinstance(args[0], dict):
            cache_args = args[0]
        else:
            cache_args = kwargs

        result, hit = await tool_cache.get_or_compute(
            tool_name,
            cache_args,
            lambda: original_arun(*args, **kwargs),
        )
        return result

    tool._arun = cached_arun
    return tool


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tool_cache_instance: Optional[ToolCache] = None


def get_tool_cache() -> Optional[ToolCache]:
    """获取全局 ToolCache 实例（懒初始化）。"""
    global _tool_cache_instance
    if _tool_cache_instance is not None:
        return _tool_cache_instance
    try:
        from src.config.settings import settings
        if not settings.tool_cache_enabled:
            return None
        _tool_cache_instance = create_default_tool_cache()
        return _tool_cache_instance
    except Exception as e:
        logger.warning("ToolCache 初始化失败: %s", e)
        return None


def create_default_tool_cache() -> ToolCache:
    """创建默认 ToolCache 实例（对齐 Node.js 配置）。"""
    configs: Dict[str, ToolCacheConfig] = {
        "retrieve_knowledge": ToolCacheConfig(
            ttl_s=300,
            max_size=50,
            embedding_key=EmbeddingKeyConfig(
                extractor=lambda args: f"{args.get('city', '')} {args.get('query', '')}",
                threshold=0.85,
            ),
        ),
        "calculate_distance": ToolCacheConfig(
            ttl_s=3600,  # 距离不会变，长缓存
            max_size=200,
        ),
        "search_hotels": ToolCacheConfig(
            ttl_s=300,
            max_size=50,
            embedding_key=EmbeddingKeyConfig(
                extractor=lambda args: f"{args.get('city', '')} {args.get('budget', '')} {args.get('level', '')}",
                threshold=0.85,
            ),
        ),
    }
    return ToolCache(configs)
