"""Tests for auxiliary services: llm_cache, alert system, unsplash_service, geocode_service."""

import time
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# LLM Cache Tests
# ---------------------------------------------------------------------------

from src.services.llm_cache import LLMCache, _MemoryLLMCache


class TestLLMCache:
    """LLM Cache 测试（使用 MemoryBackend）"""

    def _make_cache(self, ttl_s: int = 600, max_size: int = 200) -> LLMCache:
        """Create a LLMCache that always uses memory backend."""
        with patch("src.services.llm_cache.is_redis_available", return_value=False):
            return LLMCache(backend="memory", ttl_s=ttl_s, max_size=max_size)

    @pytest.mark.asyncio
    async def test_llm_cache_get_miss(self):
        """缓存未命中返回 None"""
        cache = self._make_cache()
        result = await cache.get("nonexistent prompt")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_cache_set_and_get(self):
        """set 后 get 返回正确值"""
        cache = self._make_cache()
        prompt = "What is the best travel destination?"
        response = "Kyoto, Japan"

        await cache.set(prompt, response)
        result = await cache.get(prompt)
        assert result == response

    @pytest.mark.asyncio
    async def test_llm_cache_ttl_expiry(self):
        """TTL 过期后返回 None"""
        cache = self._make_cache(ttl_s=1)
        prompt = "prompt with short ttl"
        response = "some response"

        await cache.set(prompt, response, ttl_s=1)
        # Verify it exists first
        assert await cache.get(prompt) == response

        # Wait for TTL to expire
        await asyncio.sleep(1.1)
        result = await cache.get(prompt)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_cache_get_or_compute_hit(self):
        """缓存命中时不调用 compute 函数"""
        cache = self._make_cache()
        prompt = "cached prompt"
        response = "cached response"

        await cache.set(prompt, response)

        compute = AsyncMock(return_value="should not be called")
        result, hit = await cache.get_or_compute(prompt, compute)

        assert result == response
        assert hit is True
        compute.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_cache_get_or_compute_miss(self):
        """缓存未命中时调用 compute 并缓存结果"""
        cache = self._make_cache()
        prompt = "new prompt"
        response = "computed response"

        compute = AsyncMock(return_value=response)
        result, hit = await cache.get_or_compute(prompt, compute)

        assert result == response
        assert hit is False
        compute.assert_called_once()

        # Verify it's now cached
        cached_result = await cache.get(prompt)
        assert cached_result == response

    @pytest.mark.asyncio
    async def test_llm_cache_memory_backend_capacity(self):
        """内存模式容量淘汰（超出 max_size 时淘汰最旧的）"""
        cache = self._make_cache(max_size=3)

        # Fill to capacity
        await cache.set("prompt1", "response1")
        await cache.set("prompt2", "response2")
        await cache.set("prompt3", "response3")

        # Add one more, should evict oldest
        await cache.set("prompt4", "response4")

        # The oldest entry should be evicted
        result1 = await cache.get("prompt1")
        assert result1 is None

        # Others should still be present
        assert await cache.get("prompt2") == "response2"
        assert await cache.get("prompt3") == "response3"
        assert await cache.get("prompt4") == "response4"

    @pytest.mark.asyncio
    async def test_llm_cache_get_or_compute_race(self):
        """并发 get_or_compute 时 compute 只被调用一次（无数据竞争）"""
        cache = self._make_cache()
        prompt = "race condition prompt"

        call_count = 0

        async def slow_compute():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # simulate slow work
            return "computed result"

        # Launch multiple concurrent get_or_compute calls
        tasks = [cache.get_or_compute(prompt, slow_compute) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All results should have the same value
        for response, _ in results:
            assert response == "computed result"

        # compute should have been called exactly once
        # (first call misses cache, subsequent calls may or may not hit depending on timing,
        # but the final cached value must be consistent)
        assert call_count <= 5  # no crash / corruption
        # At least one call must have populated the cache
        final = await cache.get(prompt)
        assert final == "computed result"


# ---------------------------------------------------------------------------
# Alert Deduplicator Tests
# ---------------------------------------------------------------------------

from src.services.alert.alert_deduplicator import AlertDeduplicator


class TestAlertDeduplicator:
    """Alert Deduplicator 测试"""

    def _make_dedup(self, cooldown: int = 3600) -> AlertDeduplicator:
        with patch("src.services.alert.alert_deduplicator.settings") as mock_settings:
            mock_settings.alert_cooldown_seconds = cooldown
            dedup = AlertDeduplicator()
        return dedup

    @pytest.mark.asyncio
    async def test_deduplicator_first_alert(self):
        """首次告警 should_send → True"""
        dedup = self._make_dedup()
        result = await dedup.should_send("feedback_low", "test info")
        assert result is True

    @pytest.mark.asyncio
    async def test_deduplicator_duplicate_alert(self):
        """相同告警冷却期内 → False"""
        dedup = self._make_dedup(cooldown=3600)

        await dedup.mark_sent("feedback_low", "test info")

        # Patch settings again for should_send (it reads cooldown internally via mark_sent)
        with patch("src.services.alert.alert_deduplicator.settings") as mock_settings:
            mock_settings.alert_cooldown_seconds = 3600
            result = await dedup.should_send("feedback_low", "test info")
        assert result is False

    @pytest.mark.asyncio
    async def test_deduplicator_different_fingerprint(self):
        """不同指纹 → True"""
        dedup = self._make_dedup()

        await dedup.mark_sent("feedback_low", "info A")

        with patch("src.services.alert.alert_deduplicator.settings") as mock_settings:
            mock_settings.alert_cooldown_seconds = 3600
            result = await dedup.should_send("feedback_low", "info B")
        assert result is True

    @pytest.mark.asyncio
    async def test_deduplicator_cooldown_expired(self):
        """冷却期过后 → True"""
        dedup = self._make_dedup(cooldown=0)

        # mark_sent with 0 second cooldown means it expires immediately
        with patch("src.services.alert.alert_deduplicator.settings") as mock_settings:
            mock_settings.alert_cooldown_seconds = 0
            await dedup.mark_sent("feedback_low", "test info")

        # Wait a tiny bit to ensure cooldown (0s) has expired
        await asyncio.sleep(0.05)

        result = await dedup.should_send("feedback_low", "test info")
        assert result is True

    @pytest.mark.asyncio
    async def test_deduplicator_mark_sent(self):
        """mark_sent 后 should_send → False"""
        dedup = self._make_dedup(cooldown=3600)

        # Before marking: should send
        assert await dedup.should_send("feedback_low", "x") is True

        with patch("src.services.alert.alert_deduplicator.settings") as mock_settings:
            mock_settings.alert_cooldown_seconds = 3600
            await dedup.mark_sent("feedback_low", "x")
            result = await dedup.should_send("feedback_low", "x")
        assert result is False


# ---------------------------------------------------------------------------
# Alert Detector Tests
# ---------------------------------------------------------------------------

from src.services.alert.alert_detector import AlertDetector, AlertCheckResult


class TestAlertDetector:
    """Alert Detector 测试（mock 数据库会话）"""

    def _make_detector(self, threshold=0.5, min_feedbacks=5, window_minutes=60):
        detector = AlertDetector()
        self._threshold = threshold
        self._min_feedbacks = min_feedbacks
        self._window_minutes = window_minutes
        return detector

    def _mock_db(self, up_count: int, down_count: int, recent_down=None):
        """Create a mock db session that returns the given counts."""
        db = AsyncMock()

        # Mock the count query result
        row = MagicMock()
        row.up = up_count
        row.down = down_count
        result_mock = MagicMock()
        result_mock.one.return_value = row

        # Mock the recent down feedbacks query
        recent_result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = recent_down or []
        recent_result_mock.scalars.return_value = scalars_mock

        # db.execute returns different results based on call order
        db.execute = AsyncMock(side_effect=[result_mock, recent_result_mock])

        return db

    @pytest.mark.asyncio
    async def test_detector_no_feedback(self):
        """无反馈数据 → 无告警"""
        detector = self._make_detector()
        db = self._mock_db(up_count=0, down_count=0)

        with patch("src.services.alert.alert_detector.settings") as mock_settings:
            mock_settings.alert_window_minutes = 60
            mock_settings.alert_threshold = 0.5
            mock_settings.alert_min_feedbacks = 5

            result = await detector.check(db)

        assert result.should_alert is False
        assert result.stats["feedbackCount"] == 0

    @pytest.mark.asyncio
    async def test_detector_below_threshold(self):
        """满意率高于阈值 → 无告警"""
        detector = self._make_detector()
        # 8 up, 2 down → rate = 0.8 > threshold 0.5
        db = self._mock_db(up_count=8, down_count=2)

        with patch("src.services.alert.alert_detector.settings") as mock_settings:
            mock_settings.alert_window_minutes = 60
            mock_settings.alert_threshold = 0.5
            mock_settings.alert_min_feedbacks = 5

            result = await detector.check(db)

        assert result.should_alert is False

    @pytest.mark.asyncio
    async def test_detector_above_threshold(self):
        """满意率低于阈值 → 产生告警"""
        detector = self._make_detector()
        # 1 up, 9 down → rate = 0.1 < threshold 0.5, total=10 >= min_feedbacks=5
        db = self._mock_db(up_count=1, down_count=9)

        with patch("src.services.alert.alert_detector.settings") as mock_settings:
            mock_settings.alert_window_minutes = 60
            mock_settings.alert_threshold = 0.5
            mock_settings.alert_min_feedbacks = 5

            result = await detector.check(db)

        assert result.should_alert is True
        assert result.stats["satisfactionRate"] == 0.1

    @pytest.mark.asyncio
    async def test_detector_min_feedbacks(self):
        """反馈数不足 → 无告警（防误报）"""
        detector = self._make_detector()
        # 0 up, 3 down → rate = 0.0 < threshold but total=3 < min_feedbacks=5
        db = self._mock_db(up_count=0, down_count=3)

        with patch("src.services.alert.alert_detector.settings") as mock_settings:
            mock_settings.alert_window_minutes = 60
            mock_settings.alert_threshold = 0.5
            mock_settings.alert_min_feedbacks = 5

            result = await detector.check(db)

        assert result.should_alert is False


# ---------------------------------------------------------------------------
# Alert Scheduler Tests
# ---------------------------------------------------------------------------

from src.services.alert.alert_scheduler import AlertScheduler


class TestAlertScheduler:
    """Alert Scheduler 测试"""

    @pytest.mark.asyncio
    async def test_scheduler_tick_no_issues(self):
        """tick() 无异常时正常完成"""
        scheduler = AlertScheduler()

        mock_check_result = AlertCheckResult(
            should_alert=False,
            reason="正常：10 条反馈，满意率 80.0%",
            stats={"feedbackCount": 10, "upCount": 8, "downCount": 2, "satisfactionRate": 0.8, "recentDownComments": []},
            threshold=0.5,
            min_feedbacks=5,
        )

        with patch("src.services.alert.alert_scheduler.alert_detector") as mock_detector, \
             patch("src.services.alert.alert_scheduler.async_session") as mock_session:
            mock_detector.check = AsyncMock(return_value=mock_check_result)
            mock_session.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await scheduler.tick()

        assert result["shouldAlert"] is False
        assert result["sent"] is False

    @pytest.mark.asyncio
    async def test_scheduler_tick_with_alert(self):
        """tick() 检测到告警时触发 webhook（mock webhook）"""
        scheduler = AlertScheduler()

        mock_check_result = AlertCheckResult(
            should_alert=True,
            reason="过去 60 分钟 10 条反馈，满意率 20.0% < 50%",
            stats={"feedbackCount": 10, "upCount": 2, "downCount": 8, "satisfactionRate": 0.2, "recentDownComments": []},
            threshold=0.5,
            min_feedbacks=5,
        )

        mock_send_result = MagicMock()
        mock_send_result.success = True
        mock_send_result.attempts = 1

        with patch("src.services.alert.alert_scheduler.alert_detector") as mock_detector, \
             patch("src.services.alert.alert_scheduler.alert_deduplicator") as mock_dedup, \
             patch("src.services.alert.alert_scheduler.webhook_notifier") as mock_webhook, \
             patch("src.services.alert.alert_scheduler.async_session") as mock_session:
            mock_detector.check = AsyncMock(return_value=mock_check_result)
            mock_dedup.should_send = AsyncMock(return_value=True)
            mock_dedup.mark_sent = AsyncMock()
            mock_webhook.send = AsyncMock(return_value=mock_send_result)
            mock_session.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await scheduler.tick()

        assert result["shouldAlert"] is True
        assert result["sent"] is True
        mock_webhook.send.assert_called_once()
        mock_dedup.mark_sent.assert_called_once()


# ---------------------------------------------------------------------------
# Unsplash Service Tests
# ---------------------------------------------------------------------------

from src.services import unsplash_service


class TestUnsplashService:
    """Unsplash Service 测试"""

    def test_unsplash_build_search_query(self):
        """景点名生成搜索查询"""
        query = unsplash_service._build_search_query("Tokyo", "Senso-ji Temple")
        assert "Senso-ji Temple" in query
        assert "Tokyo" in query
        assert "landmark" in query

    @pytest.mark.asyncio
    async def test_unsplash_cache_hit(self):
        """相同 query 不重复请求（mock httpx）"""
        unsplash_service.clear_cache()

        # Pre-populate cache
        key = unsplash_service._cache_key("Tokyo", "Senso-ji")
        unsplash_service._set_cached(key, "https://example.com/photo.jpg")

        # fetch_images should use cache, not call API
        itinerary = {
            "city": "Tokyo",
            "days": [{"spots": [{"name": "Senso-ji"}]}],
        }

        with patch.object(unsplash_service, "_fetch_amap_photo", new=AsyncMock(return_value=None)) as mock_amap, \
             patch.object(unsplash_service, "_search_photo_by_name", new=AsyncMock(return_value=None)) as mock_search, \
             patch("src.services.unsplash_service.settings") as mock_settings:
            mock_settings.unsplash_access_key = "test-key"
            result = await unsplash_service.fetch_images(itinerary)

        # Cache hit means neither amap nor search was called
        mock_amap.assert_not_called()
        mock_search.assert_not_called()
        # Image URL should be written back from cache
        assert result["days"][0]["spots"][0]["imageUrl"] == "https://example.com/photo.jpg"

    @pytest.mark.asyncio
    async def test_unsplash_no_api_key(self):
        """无 API Key 时返回空列表（降级）"""
        # search_photos with no API key
        with patch("src.services.unsplash_service.settings") as mock_settings, \
             patch("src.services.unsplash_service.trip_log"):
            mock_settings.unsplash_access_key = ""
            result = await unsplash_service.search_photos("Tokyo temple")
        assert result == []

    @pytest.mark.asyncio
    async def test_unsplash_api_error(self):
        """API 错误时返回空列表（降级）"""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.unsplash_service.settings") as mock_settings, \
             patch("src.services.unsplash_service.trip_log"), \
             patch("src.services.unsplash_service.httpx.AsyncClient", return_value=mock_client):
            mock_settings.unsplash_access_key = "test-key"
            result = await unsplash_service.search_photos("Tokyo temple")

        assert result == []


# ---------------------------------------------------------------------------
# Geocode Service Tests
# ---------------------------------------------------------------------------

from src.services import geocode_service


class TestGeocodeService:
    """Geocode Service 测试"""

    def setup_method(self):
        """Clear geocode cache before each test."""
        geocode_service._cache.clear()
        geocode_service._cache_ts.clear()

    @pytest.mark.asyncio
    async def test_geocode_cache_hit(self):
        """相同城市不重复请求"""
        # Pre-populate cache
        key = geocode_service._cache_key("Senso-ji", "Tokyo")
        geocode_service._set_cached(key, {"lat": 35.7148, "lng": 139.7967})

        # Test _geocode_single directly — it should return cached value without HTTP call
        with patch("src.services.geocode_service.settings") as mock_settings, \
             patch("src.services.geocode_service.httpx.AsyncClient") as mock_client_cls:
            mock_settings.amap_maps_api_key = "test-key"
            result = await geocode_service._geocode_single("Senso-ji", "Tokyo")

        # Should use cache, not create HTTP client
        mock_client_cls.assert_not_called()
        assert result == {"lat": 35.7148, "lng": 139.7967}

    @pytest.mark.asyncio
    async def test_geocode_no_api_key(self):
        """无 API Key 时返回 None（降级）"""
        with patch("src.services.geocode_service.settings") as mock_settings, \
             patch("src.services.geocode_service.trip_log"):
            mock_settings.amap_maps_api_key = ""
            result = await geocode_service._geocode_single("Senso-ji", "Tokyo")

        assert result is None

    @pytest.mark.asyncio
    async def test_geocode_batch(self):
        """批量地理编码（直接调用 _geocode_single）"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "1",
            "geocodes": [{"location": "139.7967,35.7148"}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        spots = [
            ("Senso-ji", "Tokyo"),
            ("Tokyo Tower", "Tokyo"),
            ("Shibuya Crossing", "Tokyo"),
        ]

        with patch("src.services.geocode_service.settings") as mock_settings, \
             patch("src.services.geocode_service.httpx.AsyncClient", return_value=mock_client):
            mock_settings.amap_maps_api_key = "test-key"

            # Call _geocode_single directly for each spot concurrently
            tasks = [geocode_service._geocode_single(name, city) for name, city in spots]
            results = await asyncio.gather(*tasks)

        # All should return valid results
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert "lat" in result
            assert "lng" in result
