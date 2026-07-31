"""高德地理编码服务 — 对齐 Node.js geocodeService.ts

批量地理编码 + 请求队列 + 批处理 + 内存缓存，减少 API 调用次数。
"""

import asyncio
import logging
import re
import time
from typing import Optional, Dict, Tuple

import httpx

from src.config.settings import settings
from src.services.http.retry import http_with_retry_on_429, request_id_headers
from src.utils.logger import trip_log

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
BATCH_SIZE = 10
RATE_LIMIT_S = 0.05  # 50 ms（对齐 Node.js RATE_LIMIT_MS）

# ---------------------------------------------------------------------------
# 内存缓存（相同城市名不重复请求）
# ---------------------------------------------------------------------------

_cache: Dict[str, Optional[Dict[str, float]]] = {}
_CACHE_TTL_S = 30 * 60  # 30 分钟
_cache_ts: Dict[str, float] = {}


def _cache_key(spot_name: str, city: str) -> str:
    return f"{city}:{spot_name}"


def _get_cached(key: str) -> Optional[Dict[str, float]]:
    entry = _cache.get(key)
    if entry is not None and time.time() - _cache_ts.get(key, 0) < _CACHE_TTL_S:
        return entry
    if key in _cache:
        del _cache[key]
        del _cache_ts[key]
    return None


def _set_cached(key: str, value: Optional[Dict[str, float]]) -> None:
    _cache[key] = value
    _cache_ts[key] = time.time()


def _clean_spot_name(name: str) -> str:
    """清理地点名称：去掉括号/引号及其内容，去除多余空格。"""
    n = re.sub(r'[\(\[\（「『][^\)\]\）』」]*[\)\]\）』」]', '', name)
    n = re.sub(r'[\'\"]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _normalize_spot_name(name: str, city: str) -> str:
    """分阶段地点名称归一化，按优先级尝试：
    1. 清理括号/引号
    2. 去掉描述性后缀（"-胡同漫步"、"小吃街"、"步行街"、"简餐"等）
    3. 去掉前缀（"酒店内"、"附近"、"返回"、"高铁上"等）
    返回归一化后的名称（如果去掉前缀后太短则返回空字符串）。
    """
    # Phase 1: 清理括号
    cleaned = _clean_spot_name(name)
    if not cleaned:
        return ""

    # Phase 2: 去掉描述性后缀
    descriptive_suffixes = [
        "-胡同漫步", "胡同漫步", "-步行街", "步行街",
        "小吃街", "美食街", "商业街", "简餐", "美食",
    ]
    for suffix in descriptive_suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].rstrip(" -")
            break

    # Phase 3: 去掉前缀（这些前缀后面的内容才是真正的地点）
    prefix_patterns = [
        "酒店内", "酒店", "附近", "返回", "高铁上", "车上", "机",
    ]
    for prefix in prefix_patterns:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix) + 1:
            cleaned = cleaned[len(prefix):].lstrip(" 的在内上")
            break

    return cleaned.strip()


# ---------------------------------------------------------------------------
# 请求队列 + 批处理（对齐 Node.js 的 enqueue / flushQueue）
# ---------------------------------------------------------------------------

class _GeocodeQueue:
    """异步请求队列：将并发请求聚合为批次，减少 API 调用频率。"""

    def __init__(self) -> None:
        self._pending: list = []
        self._flush_task: Optional[asyncio.Task] = None

    async def enqueue(self, spot_name: str, city: str) -> Optional[Dict[str, float]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending.append((spot_name, city, future))

        if not self._flush_task or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._schedule_flush())

        return await future

    async def _schedule_flush(self) -> None:
        await asyncio.sleep(RATE_LIMIT_S)
        await self._flush()

    async def _flush(self) -> None:
        batch = self._pending[:BATCH_SIZE]
        self._pending = self._pending[BATCH_SIZE:]

        if not batch:
            return

        tasks = []
        for spot_name, city, future in batch:
            tasks.append(self._resolve_one(spot_name, city, future))

        await asyncio.gather(*tasks, return_exceptions=True)

        # 如果还有待处理项，继续调度下一批
        if self._pending:
            self._flush_task = asyncio.create_task(self._schedule_flush())

    @staticmethod
    async def _resolve_one(spot_name: str, city: str, future: asyncio.Future) -> None:
        try:
            result = await _geocode_single(spot_name, city)
            if not future.done():
                future.set_result(result)
        except Exception as exc:
            trip_log.warning("geocode failed", err=str(exc), spot_name=spot_name, city=city)
            if not future.done():
                future.set_result(None)


_queue = _GeocodeQueue()


# ---------------------------------------------------------------------------
# 核心：单次地理编码请求
# ---------------------------------------------------------------------------

async def _geocode_single(spot_name: str, city: str) -> Optional[Dict[str, float]]:
    api_key = settings.amap_maps_api_key
    if not api_key:
        trip_log.warning("AMAP_MAPS_API_KEY not configured, skipping geocoding")
        return None

    # 尝试顺序（最多 3 次，优先级从高到低）：
    # 1. 原始完整名称（含括号定位信息，最精确）
    # 2. 仅清理括号后的名称（去掉括号内容但保留地点主体）
    # 3. 核心名（去掉描述性前后缀，最短可检索名，最后手段）
    cleaned_name = _clean_spot_name(spot_name)
    core_name = _normalize_spot_name(spot_name, city)

    # 收集候选名（按优先级去重）
    seen: set = set()
    candidates: list[str] = [spot_name]
    seen.add(spot_name)
    if cleaned_name and cleaned_name not in seen and cleaned_name != spot_name:
        candidates.append(cleaned_name)
        seen.add(cleaned_name)
    if core_name and core_name not in seen and core_name != spot_name:
        candidates.append(core_name)
        seen.add(core_name)
    
    for attempt_name in candidates:
        key = _cache_key(attempt_name, city)
        cached = _get_cached(key)
        if cached is not None:
            return cached
        
        params = {
            "key": api_key,
            "address": attempt_name,
            "city": city,
            "output": "JSON",
        }
        
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await http_with_retry_on_429(
                    client, "GET", GEOCODE_URL, params=params, headers=request_id_headers()
                )
                if resp.status_code == 429:
                    trip_log.warning(
                        "geocode rate limited (429)", status=429, spot_name=spot_name, city=city
                    )
                    return None
                resp.raise_for_status()
                data = resp.json()

            if data.get("status") == "1" and data.get("geocodes"):
                location = data["geocodes"][0].get("location", "")
                if location:
                    lng_str, lat_str = location.split(",")
                    lat, lng = float(lat_str), float(lng_str)
                    result = {"lat": lat, "lng": lng}
                    _set_cached(key, result)
                    # 同时缓存原始名称，避免下次再查
                    if attempt_name != spot_name:
                        _set_cached(_cache_key(spot_name, city), result)
                    return result

            _set_cached(key, None)
        except Exception as exc:
            trip_log.error("geocode request failed", err=str(exc), spot_name=spot_name, city=city)
            _set_cached(key, None)
    
    return None


# ---------------------------------------------------------------------------
# 对外公共接口
# ---------------------------------------------------------------------------

async def geocode_spot(spot_name: str, city: str) -> Optional[Dict[str, float]]:
    """对单个景点进行地理编码（通过队列批处理）。

    Returns:
        {"lat": ..., "lng": ...} 或 None
    """
    return await _queue.enqueue(spot_name, city)


async def enrich_trip_with_geocoding(trip_data: dict) -> None:
    """为行程数据中的每个景点补充经纬度（best-effort）。

    遍历 dailyItinerary[*] 全部 7 个时段（morning/afternoon/evening/breakfast/lunch/dinner/accommodation），
    若 slot 包含 spot 且无 latitude/longitude，则调用 geocode。
    """
    city = trip_data.get("city", "")
    daily_itinerary = trip_data.get("dailyItinerary", [])
    if not daily_itinerary or not city:
        return

    _PERIODS = ("morning", "afternoon", "evening", "breakfast", "lunch", "dinner", "accommodation")
    slots: list = []
    for day in daily_itinerary:
        for period in _PERIODS:
            slot = day.get(period)
            if slot and slot.get("spot"):
                slots.append((slot.get("spot"), slot))

    # 批量处理（每批 BATCH_SIZE 个并发）
    for i in range(0, len(slots), BATCH_SIZE):
        batch = slots[i : i + BATCH_SIZE]
        tasks = []
        for spot_name, slot in batch:
            # 跳过已有经纬度的景点
            if slot.get("latitude") is not None and slot.get("longitude") is not None:
                continue
            tasks.append(_enrich_slot(spot_name, city, slot))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def _enrich_slot(spot_name: str, city: str, slot: dict) -> None:
    result = await geocode_spot(spot_name, city)
    if result:
        slot["latitude"] = result["lat"]
        slot["longitude"] = result["lng"]
