"""Unsplash 图片服务 — 对齐 Node.js unsplash/ 目录

景点图片搜索 + 内存缓存 + Amap MCP 优先降级 Unsplash。
"""

import asyncio
import logging
import time
from typing import Optional, Dict, List

import httpx

from src.config.settings import settings
from src.services.http.retry import http_with_retry_on_429, request_id_headers
from src.utils.logger import trip_log

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

UNSPLASH_API = "https://api.unsplash.com"
SEARCH_TIMEOUT_S = 5.0
CACHE_TTL_S = 30 * 24 * 60 * 60  # 30 天
MAX_CACHE_SIZE = 1000


# ---------------------------------------------------------------------------
# 内存缓存（TTL）
# ---------------------------------------------------------------------------

_cache: Dict[str, str] = {}
_cache_ts: Dict[str, float] = {}


def _cache_key(city: str, name: str) -> str:
    return f"amap:{city}:{name}"


def _get_cached(key: str) -> Optional[str]:
    if key in _cache:
        if time.time() - _cache_ts.get(key, 0) < CACHE_TTL_S:
            return _cache[key]
        # 过期
        del _cache[key]
        del _cache_ts[key]
    return None


def _set_cached(key: str, url: str) -> None:
    # LRU 淘汰：超限时删除最早写入的条目
    if len(_cache) >= MAX_CACHE_SIZE:
        oldest_key = next(iter(_cache), None)
        if oldest_key:
            del _cache[oldest_key]
            del _cache_ts[oldest_key]
    _cache[key] = url
    _cache_ts[key] = time.time()


def clear_cache() -> None:
    """清空缓存。"""
    _cache.clear()
    _cache_ts.clear()


def cache_size() -> int:
    """返回当前缓存条目数。"""
    return len(_cache)


# ---------------------------------------------------------------------------
# Unsplash API 客户端（对齐 unsplashClient.ts）
# ---------------------------------------------------------------------------

async def search_photos(query: str, per_page: int = 3) -> List[dict]:
    """搜索景点图片。

    Args:
        query: 搜索关键词
        per_page: 返回数量（最多 30）

    Returns:
        图片信息列表 [{"url": ..., "description": ..., "photographer": ...}, ...]
    """
    access_key = settings.unsplash_access_key
    if not access_key:
        trip_log.warning(
            "UNSPLASH_ACCESS_KEY not configured, skipping Unsplash",
        )
        return []

    params = {
        "query": query,
        "per_page": per_page,
        "orientation": "landscape",
        "content_filter": "high",
    }
    headers = {"Authorization": f"Client-ID {access_key}"}
    headers.update(request_id_headers())

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_S) as client:
            # 对上游 429 做退避重试；重试耗尽仍为 429 时降级返回 []
            resp = await http_with_retry_on_429(
                client,
                "GET",
                f"{UNSPLASH_API}/search/photos",
                params=params,
                headers=headers,
            )
            if resp.status_code == 429:
                trip_log.warning("[Unsplash] search rate limited (429)")
                return []
            if resp.status_code != 200:
                trip_log.warning("[Unsplash] search failed", status=resp.status_code)
                return []

            data = resp.json()
            results = data.get("results", [])
            if not results:
                return []

            return [
                {
                    "url": photo.get("urls", {}).get("regular", ""),
                    "description": photo.get("description") or photo.get("alt_description") or "",
                    "photographer": photo.get("user", {}).get("name", "Unknown"),
                }
                for photo in results
            ]

    except Exception as exc:
        trip_log.warning("[Unsplash] search error", err=str(exc))
        return []


async def get_photo_url(photo_id: str, width: int = 800, height: int = 600) -> Optional[str]:
    """获取指定尺寸的图片 URL。

    Args:
        photo_id: Unsplash 图片 ID
        width: 目标宽度
        height: 目标高度

    Returns:
        图片 URL 字符串或 None
    """
    access_key = settings.unsplash_access_key
    if not access_key:
        return None

    params = {"w": width, "h": height, "fit": "crop"}
    headers = {"Authorization": f"Client-ID {access_key}"}
    headers.update(request_id_headers())

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_S) as client:
            # 对上游 429 做退避重试；重试耗尽仍为 429 时降级返回 None
            resp = await http_with_retry_on_429(
                client,
                "GET",
                f"{UNSPLASH_API}/photos/{photo_id}",
                params=params,
                headers=headers,
            )
            if resp.status_code == 429:
                return None
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("urls", {}).get("regular")
    except Exception as exc:
        trip_log.warning("[Unsplash] get_photo_url failed", err=str(exc), photo_id=photo_id)
        return None


# ---------------------------------------------------------------------------
# 内部：hash 选图（不同景点名尽量选不同图片）
# ---------------------------------------------------------------------------

def _simple_hash(s: str, max_val: int) -> int:
    h = 0
    for ch in s:
        h = ((h << 5) - h) + ord(ch)
    return abs(h) % max_val


async def _search_photo_by_name(query: str, name: str) -> Optional[dict]:
    """按名称 hash 从搜索结果中选图，不同名字尽量选不同图。"""
    photos = await search_photos(query, per_page=5)
    if not photos:
        return None
    idx = _simple_hash(name, len(photos))
    return photos[idx]


# ---------------------------------------------------------------------------
# Amap MCP 优先查图（对齐 imageFetcher.ts fetchAmapPhoto）
# ---------------------------------------------------------------------------

def _clean_amap_keyword(name: str) -> str:
    """清理地点名称：去掉括号/引号及其内容，去除多余空格。

    用于 Amap MCP 查询失败时的重试，提高宽泛/带后缀名称的命中率。
    例如：
      "全聚德(北京和平门店)" → "全聚德"
      "故宫博物院（北京）"   → "故宫博物院"
    """
    import re
    # 去掉中文括号()、英文括号[]、引号""''及其内容
    n = re.sub(r'[\(\[\（「『][^\)\]\）』」]*[\)\]\）』」]', '', name)
    # 去掉引号包围的内容
    n = re.sub(r'[\'\"]', '', n)
    # 合并多个空格为单个
    n = re.sub(r'\s+', ' ', n).strip()
    return n


async def _fetch_amap_photo(city: str, name: str) -> Optional[str]:
    """通过高德 MCP maps_text_search 查 POI 照片 URL。

    优化策略：
    1. 先尝试原始名称
    2. 若无结果/无图，尝试简化名称（去掉括号、引号及其中内容）
    3. 两次都失败才返回 None，触发 Unsplash 降级
    """
    from src.services.mcp.amap_client import call_tool

    # 尝试1：原始名称
    url = await _try_fetch_amap_photo(call_tool, city, name)
    if url:
        return url

    # 尝试2：简化名称（去掉括号、引号）
    cleaned = _clean_amap_keyword(name)
    if cleaned and cleaned != name:
        url = await _try_fetch_amap_photo(call_tool, city, cleaned)
        if url:
            return url

    return None


async def _try_fetch_amap_photo(call_tool, city: str, name: str) -> Optional[str]:
    """尝试通过 Amap MCP 查询单次，返回照片 URL 或 None。"""
    try:
        raw = await call_tool("maps_text_search", {"keywords": name, "city": city})
        if not raw or not raw.strip():
            return None
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logging.warning(
                "[Amap] Invalid JSON response",
                extra={"city": city, "spot_name": name, "raw_preview": raw[:100]},
            )
            return None

        pois = data.get("pois", [{}])
        if not pois:
            logging.debug("[Amap] No POIs found", extra={"city": city, "spot_name": name})
            return None

        poi = pois[0]
        photos = poi.get("photos", {})
        if isinstance(photos, dict):
            url = photos.get("url")
            if url:
                logging.debug("[Amap] Photo found", extra={"city": city, "spot_name": name, "url": url[:80]})
                return url
        logging.debug("[Amap] No photos in POI", extra={"city": city, "spot_name": name, "poi_name": poi.get("name", "?")})
        return None
    except Exception as exc:
        logging.warning(
            "[Amap] Query failed",
            extra={"err": str(exc), "city": city, "spot_name": name},
        )
        return None


# ---------------------------------------------------------------------------
# 对外公共接口：为行程附加景点图片（对齐 imageFetcher.ts fetchImages）
# ---------------------------------------------------------------------------

def _build_search_query(city: str, name: str) -> str:
    return f"{name} {city} landmark travel".strip()


def _parse_spots(itinerary: dict) -> List[dict]:
    """从行程数据中提取所有景点（去重）。"""
    spots: List[dict] = []
    city = itinerary.get("city", "")
    days = itinerary.get("days", [])
    for day in days:
        for s in day.get("spots", []):
            name = s.get("name") or s.get("spot")
            if name and city:
                spots.append({"city": city, "name": name})
    return spots


def _write_back(itinerary: dict, spot_name: str, url: str) -> None:
    """将图片 URL 写回行程数据中对应景点。"""
    for day in itinerary.get("days", []):
        for s in day.get("spots", []):
            match = s.get("name") or s.get("spot")
            if match == spot_name and not s.get("imageUrl"):
                s["imageUrl"] = url


async def fetch_images(itinerary: Optional[dict]) -> Optional[dict]:
    """为行程中的景点附加封面图片 URL（best-effort）。

    策略：优先 Amap MCP 查图 → 无结果则降级 Unsplash 搜索。
    相同景点使用缓存，避免重复请求。

    Args:
        itinerary: 行程数据字典（原地修改）

    Returns:
        修改后的 itinerary（若未配置 API Key 则原样返回）
    """
    if not itinerary:
        return itinerary

    if not settings.unsplash_access_key:
        return itinerary

    spots = _parse_spots(itinerary)
    if not spots:
        return itinerary

    # 去重
    unique: Dict[str, dict] = {}
    for s in spots:
        key = _cache_key(s["city"], s["name"])
        if key not in unique:
            unique[key] = s

    pending: Dict[str, dict] = {}

    for key, spot in unique.items():
        cached = _get_cached(key)
        if cached:
            _write_back(itinerary, spot["name"], cached)
        else:
            pending[key] = spot

    if not pending:
        return itinerary

    # 逐景点查图（Amap 优先，Unsplash 降级）
    for key, spot in pending.items():
        photo_url = await _fetch_amap_photo(spot["city"], spot["name"])
        if not photo_url:
            query = _build_search_query(spot["city"], spot["name"])
            result = await _search_photo_by_name(query, spot["name"])
            photo_url = result.get("url") if result else None

        if photo_url:
            _set_cached(key, photo_url)
            _write_back(itinerary, spot["name"], photo_url)

    return itinerary


# ---------------------------------------------------------------------------
# 适配 dailyItinerary 格式（trip_service.py 使用）
# ---------------------------------------------------------------------------

async def enrich_trip_with_images(parsed: dict) -> None:
    """为行程数据中的景点附加图片 URL。

    同���兼容 Node.js 的 dailyItinerary 格式和 days/spots 格式：
    - days[*].spots[*]（imageFetcher 格式）
    - dailyItinerary[*].{morning,afternoon,evening,breakfast,lunch,dinner,accommodation}（geocodeService 格式）
    """
    # 有 dailyItinerary → 适配转换，拼装 days[*].spots[*] 结构供 fetch_images 使用
    # 修复：原条件 `daily_itinerary and not parsed.get("days")` 在 parsed 同时存在
    # dailyItinerary 和 days（整数，表示总天数）时误入 else 分支，导致 _parse_spots
    # 因 days 不是列表而 TypeError 失败。现在只要 dailyItinerary 存在就走适配路径。
    daily_itinerary = parsed.get("dailyItinerary", [])
    if daily_itinerary:
        # 转换格式：dailyItinerary[*].{morning,...,accommodation} → days[*].spots
        # 覆盖全部 7 个时段，包括餐饮和住宿
        _PERIODS = ("morning", "afternoon", "evening", "breakfast", "lunch", "dinner", "accommodation")
        days = []
        slot_period_map: list[list[str]] = []  # 记录每个 spot 对应的 period，用于回写
        for day in daily_itinerary:
            spots = []
            day_periods = []
            for period in _PERIODS:
                slot = day.get(period)
                if slot and slot.get("spot"):
                    spots.append({"name": slot["spot"], "spot": slot["spot"], "_period": period})
                    day_periods.append(period)
            days.append({"spots": spots})
            slot_period_map.append(day_periods)

        temp_itinerary = {"city": parsed.get("city", ""), "days": days}
        await fetch_images(temp_itinerary)

        # 将 imageUrl 回写到原始 dailyItinerary 的 slot
        for day_data, temp_day, day_periods in zip(daily_itinerary, days, slot_period_map):
            for period, temp_spot in zip(day_periods, temp_day["spots"]):
                slot = day_data.get(period)
                if slot and temp_spot.get("imageUrl"):
                    slot["imageUrl"] = temp_spot["imageUrl"]
    else:
        await fetch_images(parsed)
