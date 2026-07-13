"""最短通勤择优服务。

给定「当前位置 + 若干候选目的地 + 出行方式」，并行调用高德 v5 Direction API
计算真实路网通勤时长，按耗时升序排序并标记耗时最短者为推荐项。

设计要点：
- 坐标解析：候选若自带 lat/lng 直接用；否则用 name/address + city 走地理编码
  （复用 src.services.geocode_service.geocode_spot）。
- 真实路网：区别于 calculate_distance.py 的 Haversine 直线估算，这里拿的是
  驾车/步行/公交/骑行的真实耗时与距离。
- 并行：所有候选用 asyncio.gather 并发计算。
- 容错：单个候选失败（地理编码失败 / 路线规划失败）不影响其余，计入 errors。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.config.settings import settings
from src.services.geocode_service import geocode_spot

logger = logging.getLogger(__name__)

AMAP_DIRECTION_BASE = "https://restapi.amap.com"

# 出行方式 -> 高德 v5 Direction endpoint
# driving/walking/cycling 用 v5（bicycling 的 v3 已停服：SERVICE_NOT_AVAILABLE）；
# transit 用 v3，因为 v3 的 city 接受「城市名」，而 v5 的 city1/city2 只接受 citycode，
# 且前端常只传城市名（甚至为空），v3 更友好。
MODE_ENDPOINTS: Dict[str, str] = {
    "driving": "/v5/direction/driving",
    "walking": "/v5/direction/walking",
    "transit": "/v3/direction/transit/integrated",
    "cycling": "/v5/direction/bicycling",
}

VALID_MODES = set(MODE_ENDPOINTS.keys())

# 轻量内存缓存（路线有时效性，TTL 较短）
_ROUTE_CACHE: Dict[str, Dict[str, Any]] = {}
_ROUTE_CACHE_TS: Dict[str, float] = {}
_ROUTE_TTL_S = 300  # 5 分钟


async def _reverse_geocode_city(lat: float, lng: float) -> Optional[str]:
    """由坐标反查所在城市（transit 必填 city）。失败返回 None。"""
    api_key = settings.amap_maps_api_key
    if not api_key:
        return None
    url = "https://restapi.amap.com/v3/geocode/regeo"
    params = {
        "key": api_key,
        "location": f"{lng},{lat}",
        "extensions": "base",
        "output": "JSON",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") == "1":
            comp = data.get("regeocode", {}).get("addressComponent", {})
            city = comp.get("city") or comp.get("province") or ""
            city = city.rstrip("市").rstrip("省").strip() if city else ""
            return city or None
    except Exception as exc:
        logger.warning("reverse geocode failed for %s,%s: %s", lat, lng, exc)
    return None


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------

async def compute_optimal_commute(
    origin: Dict[str, float],
    destinations: List[Dict[str, Any]],
    mode: str,
    city: Optional[str] = None,
) -> Dict[str, Any]:
    """计算最短通勤并择优。

    Args:
        origin: {"lat": ..., "lng": ...}
        destinations: 候选列表，元素含 name/id/lat/lng/city/address
        mode: driving / walking / transit / cycling
        city: 当前城市（transit 需要）

    Returns:
        {
            "origin": {...}, "mode": str,
            "results": [...], "recommended": {...} | None,
            "errors": [{"name":..., "error":...}]
        }
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"不支持的出行方式：{mode}，可选 {sorted(VALID_MODES)}"
        )

    # 公交(transit) 必须带城市：用户未填时，由起点反查城市（一次即可，供所有候选复用）
    if mode == "transit" and not city:
        try:
            city = await _reverse_geocode_city(origin["lat"], origin["lng"])
        except Exception:
            city = None

    tasks = [
        _resolve_and_route(origin, dest, mode, city) for dest in destinations
    ]
    items = await asyncio.gather(*tasks)

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for it in items:
        if it.get("error"):
            errors.append({"name": it.get("name"), "error": it["error"]})
        else:
            results.append(it)

    results.sort(key=lambda x: x["duration_sec"])
    recommended = results[0] if results else None

    return {
        "origin": origin,
        "mode": mode,
        "results": results,
        "recommended": recommended,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# 单候选：解析坐标 -> 路径规划
# ---------------------------------------------------------------------------

async def _resolve_and_route(
    origin: Dict[str, float],
    dest: Dict[str, Any],
    mode: str,
    city: Optional[str],
) -> Dict[str, Any]:
    name = dest.get("name") or dest.get("address") or "目的地"

    coords: Optional[Tuple[float, float]] = None
    if dest.get("lat") is not None and dest.get("lng") is not None:
        coords = (float(dest["lat"]), float(dest["lng"]))
    else:
        # 地理编码回退
        gc_city = dest.get("city") or city
        query = dest.get("address") or dest.get("name")
        if query and gc_city:
            try:
                geo = await geocode_spot(query, gc_city)
            except Exception as exc:  # 地理编码异常不应中断整体
                logger.warning("geocode failed for %s: %s", query, exc)
                geo = None
            if geo:
                coords = (geo["lat"], geo["lng"])

    if not coords:
        return {
            "name": name,
            "error": "无法解析坐标（缺少经纬度且地理编码失败，请检查名称/城市）",
        }

    try:
        route = await _direction(origin, coords, mode, city or dest.get("city"))
    except Exception as exc:
        logger.warning("direction failed for %s: %s", name, exc)
        return {"name": name, "error": f"路径规划失败：{exc}"}

    if route is None:
        return {"name": name, "error": "未找到可行路线"}

    return {
        "id": dest.get("id"),
        "name": name,
        "duration_sec": route["duration_sec"],
        "distance_m": route["distance_m"],
        "transfers": route.get("transfers"),
        "polyline": route.get("polyline"),
        "lat": coords[0],
        "lng": coords[1],
        **{k: v for k, v in route.items() if k not in ("duration_sec", "distance_m", "polyline")},
    }


# ---------------------------------------------------------------------------
# 高德 v5 Direction 调用
# ---------------------------------------------------------------------------

async def _direction(
    origin: Dict[str, float],
    dest_coords: Tuple[float, float],
    mode: str,
    city: Optional[str],
) -> Optional[Dict[str, Any]]:
    """调用高德 v5 Direction，返回标准化 {duration_sec, distance_m, transfers?, polyline?}。"""
    cache_key = (
        f"{mode}:{origin['lng']},{origin['lat']}:"
        f"{dest_coords[1]},{dest_coords[0]}:{city}"
    )
    if cache_key in _ROUTE_CACHE and (
        time.time() - _ROUTE_CACHE_TS.get(cache_key, 0) < _ROUTE_TTL_S
    ):
        return _ROUTE_CACHE[cache_key]

    api_key = settings.amap_maps_api_key
    if not api_key:
        raise RuntimeError("高德 API Key 未配置（amap_maps_api_key）")

    endpoint = MODE_ENDPOINTS[mode]
    params: Dict[str, Any] = {
        "key": api_key,
        "origin": f"{origin['lng']},{origin['lat']}",
        "destination": f"{dest_coords[1]},{dest_coords[0]}",
    }
    if mode == "transit":
        if not city:
            raise RuntimeError("公交路线规划缺少城市信息，请填写起点城市（或确保起点可被识别）")
        params["city"] = city  # v3 公交：city 为起点城市（城市名或 adcode 均可）
        # v3 公交默认即返回 duration / distance，无需 show_fields
    else:
        params["show_fields"] = "cost,polyline"

    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(AMAP_DIRECTION_BASE + endpoint, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        raise RuntimeError(data.get("info") or "高德路径规划返回错误")

    parsed = _parse_route(data, mode)
    if parsed is not None:
        _ROUTE_CACHE[cache_key] = parsed
        _ROUTE_CACHE_TS[cache_key] = time.time()
    return parsed


def _parse_route(data: Dict[str, Any], mode: str) -> Optional[Dict[str, Any]]:
    """从 v5 Direction 响应中解析标准化字段。"""
    route = data.get("route", {})

    if mode == "transit":
        transits = route.get("transits", [])
        if not transits:
            return None
        best = transits[0]
        # v3 公交：duration / distance 直接在 transit 顶层（秒 / 米，字符串）
        duration = int(float(best.get("duration") or 0))
        distance = int(float(best.get("distance") or 0))
        segments = best.get("segments", [])
        transfers = max(0, len(segments) - 1)

        # ---- 提取地铁/公交线路信息 ----
        transit_lines: List[str] = []
        has_subway = False
        # ---- 提取完整行程段详情（用于前端展示逐步过程） ----
        steps_detail: List[Dict[str, Any]] = []
        for seg in segments:
            bus_info = seg.get("bus") or {}
            walk_info = seg.get("walking") or {}

            # 步行段
            if walk_info:
                walk_dist = int(float(walk_info.get("distance") or 0))
                walk_dur = int(float(walk_info.get("duration") or 0))
                if walk_dur > 0 or walk_dist > 0:
                    steps_detail.append({
                        "type": "walking",
                        "label": "步行",
                        "distance_m": walk_dist,
                        "duration_sec": walk_dur,
                    })

            # 公交 / 地铁段
            for bl in bus_info.get("buslines", []):
                line_name = bl.get("name", "")
                if line_name:
                    transit_lines.append(line_name)
                    bl_type = bl.get("type", "")
                    is_subway = "地铁" in line_name or bl_type == "subway"
                    if is_subway:
                        has_subway = True

                    departure_stop = bl.get("departure_stop", {}).get("name", "") or seg.get("departure", {}).get("name", "")
                    arrival_stop = bl.get("arrival_stop", {}).get("name", "") or seg.get("arrival", {}).get("name", "")

                    steps_detail.append({
                        "type": "subway" if is_subway else "bus",
                        "label": line_name,
                        "departure": departure_stop,
                        "arrival": arrival_stop,
                        "distance_m": int(float(bl.get("distance") or 0)),
                        "duration_sec": int(float(bl.get("duration") or 0)),
                        "via_stops": min(int(bl.get("via_num") or 0), 99),
                    })

            # 无 buslines 的公交段（如纯步行换乘）
            if not bus_info.get("buslines") and bus_info:
                steps_detail.append({
                    "type": "transfer_walk",
                    "label": "站内换乘步行",
                    "distance_m": int(float(walk_info.get("distance") or 0)),
                    "duration_sec": int(float(walk_info.get("duration") or 0)),
                })

        # ---- 拼接所有步行段的 polyline（公交/地铁段无 polyline，用步行段近似） ----
        walking_polylines: List[str] = []
        for seg in segments:
            walk = seg.get("walking") or {}
            for step in walk.get("steps", []):
                p = step.get("polyline")
                if p:
                    walking_polylines.append(p)
        polyline = ";".join(walking_polylines) if walking_polylines else None

        result = {
            "duration_sec": duration,
            "distance_m": distance,
            "transfers": transfers,
            "polyline": polyline,
            "has_subway": has_subway,
            "transit_lines": transit_lines,
            "steps_detail": steps_detail,
        }
        return result

    paths = route.get("paths", [])
    if not paths:
        return None
    best = paths[0]
    cost = best.get("cost", {})
    duration = int(cost.get("duration") or best.get("duration") or 0)
    distance = int(best.get("distance") or 0)
    # v5 的 polyline 不在 path 顶层，而在各 step 中（明文 "lng,lat;lng,lat"）。
    # 优先拼接各 step 的 polyline；若 path 顶层意外有值也兼容。
    polyline = best.get("polyline")
    if not polyline:
        step_polys = [
            s.get("polyline") for s in (best.get("steps") or []) if s.get("polyline")
        ]
        if step_polys:
            polyline = ";".join(step_polys)
    return {
        "duration_sec": duration,
        "distance_m": distance,
        "polyline": polyline,
    }


# ---------------------------------------------------------------------------
# 输入联想（高德 /v3/assistant/inputtips）
# ---------------------------------------------------------------------------

async def search_input_tips(
    keywords: str, city: Optional[str] = None, limit: int = 10
) -> List[Dict[str, Any]]:
    """调用高德输入提示接口，返回联想结果列表。

    Returns:
        [{"name", "address?", "district?", "lat?", "lng?"}, ...]
    """
    api_key = settings.amap_maps_api_key
    if not api_key:
        return []

    params: Dict[str, Any] = {
        "key": api_key,
        "keywords": keywords,
        "datatype": "all",
        "output": "JSON",
    }
    if city:
        params["city"] = city

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{AMAP_DIRECTION_BASE}/v3/assistant/inputtips", params=params
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        return []

    tips: List[Dict[str, Any]] = []
    for t in data.get("tips", []):
        if not t.get("name") or t.get("location") is None:
            continue
        loc_parts = str(t["location"]).split(",")
        if len(loc_parts) != 2:
            continue
        try:
            lng, lat = float(loc_parts[0]), float(loc_parts[1])
        except (ValueError, IndexError):
            continue
        tips.append({
            "name": t["name"],
            "address": t.get("address") or t.get("district") or "",
            "district": t.get("district") or "",
            "lat": lat,
            "lng": lng,
        })
        if len(tips) >= limit:
            break
    return tips
