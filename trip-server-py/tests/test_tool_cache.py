"""ToolCache 单元测试

对标 Node.js trip-server/src/services/llmGuard/__tests__/toolCache.test.ts。

覆盖：
- get_or_compute 命中/未命中
- 字面 key 归一化：trim + lowercase + sort keys + skip None
- embedding 归一化：相似 query 命中、阈值边界、跨城市不命中
- compute 失败时不写入缓存
- 未配置的 tool 直接调 compute
- 不同 tool 的 key namespace 隔离
- TTL 过期
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from src.services.agent.tool_cache import (
    EmbeddingKeyConfig,
    ToolCache,
    ToolCacheConfig,
    _dot_product,
    _make_literal_key,
)


# ---------------------------------------------------------------------------
# Mock Redis：让 ToolCache 降级到 _MemoryBackend
# ---------------------------------------------------------------------------

MOCK_REDIS_PATCH = {
    "src.services.agent.tool_cache.get_redis": lambda: None,
    "src.services.agent.tool_cache.is_redis_available": lambda: False,
}


def _make_cache(
    configs: dict[str, ToolCacheConfig],
) -> ToolCache:
    """创建使用内存后端的 ToolCache。"""
    with patch("src.services.agent.tool_cache.is_redis_available", return_value=False):
        return ToolCache(configs, backend="memory")


# ---------------------------------------------------------------------------
# Deterministic mock embedder（对标 Node.js 测试中的 makeMockEmbedder）
# ---------------------------------------------------------------------------


async def _mock_embedder(text: str) -> list[float]:
    """基于"语义关键词"返回固定 4 维向量。

    向量设计（已 L2 normalize）：
    - [0.95, 0.31, 0, 0] = "成都+美食类"
    - [0.31, 0.95, 0, 0] = "成都+景点类"
    - [0, 0, 1, 0]       = "北京"
    - [0, 0, 0, 1]       = "其他"

    cosine sim（dot product，已 normalize）：
    - 美食 vs 美食 = 1.0
    - 美食 vs 景点 = 0.95*0.31 + 0.31*0.95 = 0.589
    - 美食 vs 北京 = 0
    """
    if "成都" in text and any(k in text for k in ("food", "美食", "好吃", "川菜", "小吃")):
        return [0.95, 0.31, 0, 0]
    if "成都" in text and any(k in text for k in ("景点", "必去", "历史文化", "亲子")):
        return [0.31, 0.95, 0, 0]
    if "北京" in text:
        return [0, 0, 1, 0]
    return [0, 0, 0, 1]


# ===================================================================
# 基础功能
# ===================================================================


class TestBasicFunctionality:
    """基础功能测试（~8 个）。"""

    @pytest.mark.asyncio
    async def test_cache_miss_then_compute(self):
        """首次调用：miss，compute 并写入。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="sunny 25°C")

        result, hit = await cache.get_or_compute("get_weather", {"city": "成都"}, compute)

        assert hit is False
        assert result == "sunny 25°C"
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_hit_same_key(self):
        """相同 key 再次调用：hit，不再 compute。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="sunny 25°C")

        await cache.get_or_compute("get_weather", {"city": "成都"}, compute)
        result, hit = await cache.get_or_compute("get_weather", {"city": "成都"}, compute)

        assert hit is True
        assert result == "sunny 25°C"
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_ttl_expired_miss(self):
        """TTL 过期后 cache miss。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=1, max_size=10)})
        compute = AsyncMock(return_value="sunny")

        await cache.get_or_compute("get_weather", {"city": "成都"}, compute)
        assert compute.await_count == 1

        # 模拟时间流逝超过 TTL
        # 手动修改 cache entry 的 created_at
        backend = cache._caches["get_weather"]
        for key in list(backend._store.keys()):
            backend._store[key].created_at = time.time() - 2  # 2s ago > 1s TTL

        result, hit = await cache.get_or_compute("get_weather", {"city": "成都"}, compute)
        assert hit is False
        assert compute.await_count == 2

    @pytest.mark.asyncio
    async def test_different_tool_name_isolated(self):
        """不同 tool name 隔离：weather 的缓存不影响 knowledge。"""
        cache = _make_cache({
            "get_weather": ToolCacheConfig(ttl_s=60, max_size=10),
            "retrieve_knowledge": ToolCacheConfig(ttl_s=60, max_size=10),
        })

        await cache.get_or_compute("get_weather", {"city": "成都"}, AsyncMock(return_value="weather:成都"))
        result, hit = await cache.get_or_compute(
            "retrieve_knowledge", {"city": "成都"}, AsyncMock(return_value="knowledge:成都景点")
        )

        assert result == "knowledge:成都景点"
        assert hit is False  # 不会命中 weather 的缓存

    @pytest.mark.asyncio
    async def test_unconfigured_tool_always_compute(self):
        """未配置的 tool：直接调 compute，不写缓存。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="distance result")

        r1, hit1 = await cache.get_or_compute("calculate_distance", {"from": "北京", "to": "上海"}, compute)
        r2, hit2 = await cache.get_or_compute("calculate_distance", {"from": "北京", "to": "上海"}, compute)

        assert hit1 is False
        assert hit2 is False
        assert compute.await_count == 2

    @pytest.mark.asyncio
    async def test_compute_failure_not_cached(self):
        """compute 失败：不写入缓存，下次重新调。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(side_effect=[RuntimeError("wttr.in 500"), "sunny 25°C"])

        with pytest.raises(RuntimeError, match="wttr.in 500"):
            await cache.get_or_compute("get_weather", {"city": "成都"}, compute)

        result, hit = await cache.get_or_compute("get_weather", {"city": "成都"}, compute)
        assert hit is False
        assert result == "sunny 25°C"
        assert compute.await_count == 2

    @pytest.mark.asyncio
    async def test_stats_compute_called_once_on_hit(self):
        """stats: 命中时 compute 只调一次。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="sunny")

        for _ in range(5):
            await cache.get_or_compute("get_weather", {"city": "成都"}, compute)

        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_different_args_different_key(self):
        """不同参数值 → 未命中。"""
        cache = _make_cache({"search_hotels": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(side_effect=["hotel A", "hotel B"])

        r1, hit1 = await cache.get_or_compute("search_hotels", {"city": "北京", "budget": 500}, compute)
        r2, hit2 = await cache.get_or_compute("search_hotels", {"city": "北京", "budget": 800}, compute)

        assert hit1 is False
        assert hit2 is False
        assert r1 == "hotel A"
        assert r2 == "hotel B"
        assert compute.await_count == 2


# ===================================================================
# 字面归一化
# ===================================================================


class TestLiteralNormalization:
    """字面 key 归一化测试（~6 个）。"""

    @pytest.mark.asyncio
    async def test_trim_whitespace_hit(self):
        """trim 空格 → 命中。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="sunny")

        await cache.get_or_compute("get_weather", {"city": "成都"}, compute)
        _, hit = await cache.get_or_compute("get_weather", {"city": "  成都  "}, compute)

        assert hit is True
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_lowercase_string_hit(self):
        """string 字段 lowercase → 命中。"""
        cache = _make_cache({"retrieve_knowledge": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="result")

        await cache.get_or_compute("retrieve_knowledge", {"query": "CHENGDU", "city": "北京"}, compute)
        _, hit = await cache.get_or_compute("retrieve_knowledge", {"query": "chengdu", "city": "北京"}, compute)

        assert hit is True
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_sorted_keys_hit(self):
        """排序 keys 让 {a, b} == {b, a} → 命中。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="result")

        await cache.get_or_compute("get_weather", {"city": "成都", "date": "2026-06-27"}, compute)
        _, hit = await cache.get_or_compute("get_weather", {"date": "2026-06-27", "city": "成都"}, compute)

        assert hit is True
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_skip_none_fields_hit(self):
        """跳过 None 字段 → {city, budget=None, level=None} == {city} → 命中。"""
        cache = _make_cache({"search_hotels": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="hotel result")

        await cache.get_or_compute("search_hotels", {"city": "北京", "budget": None, "level": None}, compute)
        _, hit = await cache.get_or_compute("search_hotels", {"city": "北京"}, compute)

        assert hit is True
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_empty_args_hit(self):
        """空参数 → 命中。"""
        cache = _make_cache({"get_weather": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(return_value="default")

        await cache.get_or_compute("get_weather", {}, compute)
        _, hit = await cache.get_or_compute("get_weather", {}, compute)

        assert hit is True
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_different_numeric_values_miss(self):
        """数字字段不同 → 未命中。"""
        cache = _make_cache({"search_hotels": ToolCacheConfig(ttl_s=60, max_size=10)})
        compute = AsyncMock(side_effect=["r1", "r2"])

        await cache.get_or_compute("search_hotels", {"city": "北京", "budget": 500}, compute)
        _, hit = await cache.get_or_compute("search_hotels", {"city": "北京", "budget": 800}, compute)

        assert hit is False
        assert compute.await_count == 2


# ===================================================================
# Embedding 归一化
# ===================================================================


class TestEmbeddingNormalization:
    """embedding 归一化路径测试（~8 个）。"""

    def _emb_cache(
        self,
        tool_name: str = "retrieve_knowledge",
        threshold: float = 0.85,
        embedder=None,
        extractor=None,
    ) -> ToolCache:
        if embedder is None:
            embedder = _mock_embedder
        if extractor is None:
            extractor = lambda a: f"{a.get('city', '')} {a.get('category', '')} {a.get('query', '')}"
        return _make_cache({
            tool_name: ToolCacheConfig(
                ttl_s=60,
                max_size=100,
                embedding_key=EmbeddingKeyConfig(
                    extractor=extractor,
                    threshold=threshold,
                    embedder=embedder,
                ),
            ),
        })

    @pytest.mark.asyncio
    async def test_similar_query_hit(self):
        """语义相似参数 → cosine > threshold → 命中（成都美食 ≈ 成都好吃）。"""
        cache = self._emb_cache()
        compute = AsyncMock(side_effect=["result: 成都美食列表", "result: 不应被调"])

        await cache.get_or_compute(
            "retrieve_knowledge",
            {"city": "成都", "category": "food", "query": "美食"},
            compute,
        )
        result, hit = await cache.get_or_compute(
            "retrieve_knowledge",
            {"city": "成都", "category": "food", "query": "好吃的"},
            compute,
        )

        assert hit is True
        assert result == "result: 成都美食列表"
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_different_topic_miss(self):
        """不同主题不命中（成都美食 vs 成都景点，sim=0.589 < 0.85）。"""
        cache = self._emb_cache()
        compute = AsyncMock(side_effect=["result: 成都美食", "result: 成都景点"])

        await cache.get_or_compute(
            "retrieve_knowledge",
            {"city": "成都", "category": "food", "query": "美食"},
            compute,
        )
        result, hit = await cache.get_or_compute(
            "retrieve_knowledge",
            {"city": "成都", "category": "attraction", "query": "景点"},
            compute,
        )

        assert hit is False
        assert result == "result: 成都景点"
        assert compute.await_count == 2

    @pytest.mark.asyncio
    async def test_cross_city_miss(self):
        """跨城市不命中（成都美食 vs 北京美食，sim=0）。"""
        cache = self._emb_cache()
        compute = AsyncMock(side_effect=["result: 成都美食", "result: 北京美食"])

        await cache.get_or_compute(
            "retrieve_knowledge",
            {"city": "成都", "category": "food", "query": "美食"},
            compute,
        )
        result, hit = await cache.get_or_compute(
            "retrieve_knowledge",
            {"city": "北京", "category": "food", "query": "美食"},
            compute,
        )

        assert hit is False
        assert result == "result: 北京美食"
        assert compute.await_count == 2

    @pytest.mark.asyncio
    async def test_threshold_boundary_exact_hit(self):
        """阈值边界：sim=0.85, threshold=0.85 → 命中。"""
        # a = [1, 0], b = [0.85, 0.527] → dot ≈ 0.85
        async def pair_embedder(text: str) -> list[float]:
            if text == "first":
                return [1.0, 0.0]
            if text == "second":
                return [0.85, 0.527]
            return [1.0, 0.0]

        # 使用可变 extractor 来控制两次返回不同的文本
        call_count = {"n": 0}

        def switching_extractor(args: dict) -> str:
            call_count["n"] += 1
            return "first" if call_count["n"] == 1 else "second"

        cache = _make_cache({
            "test": ToolCacheConfig(
                ttl_s=60,
                max_size=10,
                embedding_key=EmbeddingKeyConfig(
                    extractor=switching_extractor,
                    threshold=0.85,
                    embedder=pair_embedder,
                ),
            ),
        })
        compute = AsyncMock(return_value="result")

        await cache.get_or_compute("test", {"q": "first"}, compute)
        _, hit = await cache.get_or_compute("test", {"q": "second"}, compute)

        assert hit is True
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_threshold_boundary_above_miss(self):
        """阈值边界：sim=0.85, threshold=0.86 → 未命中。"""
        async def pair_embedder(text: str) -> list[float]:
            if text == "a":
                return [1.0, 0.0]
            if text == "b":
                return [0.85, 0.527]
            return [1.0, 0.0]

        cache = _make_cache({
            "test": ToolCacheConfig(
                ttl_s=60,
                max_size=10,
                embedding_key=EmbeddingKeyConfig(
                    extractor=lambda a: a.get("q", ""),
                    threshold=0.86,
                    embedder=pair_embedder,
                ),
            ),
        })
        compute = AsyncMock(return_value="r")

        await cache.get_or_compute("test", {"q": "a"}, compute)
        _, hit = await cache.get_or_compute("test", {"q": "b"}, compute)

        assert hit is False  # sim=0.85 < threshold=0.86

    @pytest.mark.asyncio
    async def test_empty_cache_miss(self):
        """空 cache 直接 miss。"""
        cache = self._emb_cache(extractor=lambda a: "x")
        compute = AsyncMock(return_value="result")

        _, hit = await cache.get_or_compute("retrieve_knowledge", {"city": "成都"}, compute)

        assert hit is False
        assert compute.await_count == 1

    @pytest.mark.asyncio
    async def test_compute_failure_not_cached_embedding(self):
        """embedding 路径 compute 失败时不写 cache。"""
        cache = self._emb_cache(
            tool_name="test",
            extractor=lambda a: "x",
        )
        compute = AsyncMock(side_effect=[RuntimeError("RAG fail"), "result"])

        with pytest.raises(RuntimeError, match="RAG fail"):
            await cache.get_or_compute("test", {"q": "a"}, compute)

        _, hit = await cache.get_or_compute("test", {"q": "a"}, compute)
        assert hit is False
        assert compute.await_count == 2

    @pytest.mark.asyncio
    async def test_extractor_text_sent_to_embedder(self):
        """extractor 拼出来的字符串送入 embedder。"""
        seen_texts: list[str] = []

        async def track_embedder(text: str) -> list[float]:
            seen_texts.append(text)
            return [1, 0, 0, 0]

        cache = _make_cache({
            "test": ToolCacheConfig(
                ttl_s=60,
                max_size=10,
                embedding_key=EmbeddingKeyConfig(
                    extractor=lambda a: f"{a.get('city', '')}|{a.get('category', '')}|{a.get('query', '')}",
                    threshold=0.85,
                    embedder=track_embedder,
                ),
            ),
        })

        await cache.get_or_compute(
            "test",
            {"city": "成都", "category": "food", "query": "美食"},
            AsyncMock(return_value="r"),
        )
        await cache.get_or_compute(
            "test",
            {"city": "北京", "category": "food", "query": "美食"},
            AsyncMock(return_value="r"),
        )

        assert seen_texts == ["成都|food|美食", "北京|food|美食"]


# ===================================================================
# Helper 单元测试
# ===================================================================


class TestHelpers:
    """辅助函数测试。"""

    def test_dot_product_identical(self):
        assert _dot_product([1, 0], [1, 0]) == 1.0

    def test_dot_product_orthogonal(self):
        assert _dot_product([1, 0], [0, 1]) == 0.0

    def test_dot_product_partial(self):
        # 0.95*0.31 + 0.31*0.95 ≈ 0.589
        sim = _dot_product([0.95, 0.31, 0, 0], [0.31, 0.95, 0, 0])
        assert abs(sim - 0.589) < 0.001

    def test_literal_key_sorted_keys(self):
        k1 = _make_literal_key("t", {"a": "1", "b": "2"})
        k2 = _make_literal_key("t", {"b": "2", "a": "1"})
        assert k1 == k2

    def test_literal_key_trim_lowercase(self):
        k1 = _make_literal_key("t", {"query": "CHENGDU"})
        k2 = _make_literal_key("t", {"query": "  chengdu  "})
        assert k1 == k2

    def test_literal_key_skip_none(self):
        k1 = _make_literal_key("t", {"city": "北京", "budget": None})
        k2 = _make_literal_key("t", {"city": "北京"})
        assert k1 == k2

    def test_literal_key_different_tool_isolated(self):
        k1 = _make_literal_key("weather", {"city": "成都"})
        k2 = _make_literal_key("knowledge", {"city": "成都"})
        assert k1 != k2
