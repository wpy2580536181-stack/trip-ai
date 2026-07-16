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

# 公交/地铁线路完整几何缓存（线路变化极少，缓存 1 天）
_BUSLINE_CACHE: Dict[str, Optional[str]] = {}
_BUSLINE_CACHE_TS: Dict[str, float] = {}
_BUSLINE_TTL_S = 86400


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
    compare_modes: bool = False,
    waypoints: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """计算最短通勤并择优。

    Args:
        origin: {"lat": ..., "lng": ...}
        destinations: 候选列表，元素含 name/id/lat/lng/city/address
        mode: driving / walking / transit / cycling
        city: 当前城市（transit 需要）
        compare_modes: 为 true 时额外计算其余 3 种方式，返回 per_mode 横向对比
        waypoints: 途经点列表（多段通勤），起点到候选之间依次经过

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

    wps = waypoints or []
    tasks = [
        _resolve_and_route(origin, dest, mode, city, compare_modes, wps)
        for dest in destinations
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

async def _resolve_coords(
    dest: Dict[str, Any], city: Optional[str]
) -> Tuple[Optional[Tuple[float, float]], str]:
    """解析候选坐标：自带经纬度直接用，否则地理编码回退。返回 (coords, name)。"""
    name = dest.get("name") or dest.get("address") or "目的地"
    coords: Optional[Tuple[float, float]] = None
    if dest.get("lat") is not None and dest.get("lng") is not None:
        coords = (float(dest["lat"]), float(dest["lng"]))
    else:
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
    return coords, name


async def _resolve_and_route(
    origin: Dict[str, float],
    dest: Dict[str, Any],
    mode: str,
    city: Optional[str],
    compare_modes: bool = False,
    waypoints: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    coords, name = await _resolve_coords(dest, city)
    if not coords:
        return {
            "name": name,
            "error": "无法解析坐标（缺少经纬度且地理编码失败，请检查名称/城市）",
        }

    # 解析途经点坐标（多段通勤）
    wp_coords: List[Tuple[float, float]] = []
    if waypoints:
        for wp in waypoints:
            wc, wn = await _resolve_coords(wp, city)
            if not wc:
                return {
                    "name": name,
                    "error": f"途经点「{wn}」无法解析坐标，请检查名称/城市",
                }
            wp_coords.append(wc)

    # 有序点列：[起点, 途经点..., 候选]
    points: List[Tuple[float, float]] = [
        (origin["lat"], origin["lng"]),
        *wp_coords,
        coords,
    ]

    try:
        route = await _route_points(points, mode, city or dest.get("city"))
    except Exception as exc:
        logger.warning("direction failed for %s: %s", name, exc)
        return {"name": name, "error": f"路径规划失败：{exc}"}

    if route is None:
        return {"name": name, "error": "未找到可行路线"}

    item: Dict[str, Any] = {
        "id": dest.get("id"),
        "name": name,
        "duration_sec": route["duration_sec"],
        "distance_m": route["distance_m"],
        "transfers": route.get("transfers"),
        "polyline": route.get("polyline"),
        "polyline_segments": route.get("polyline_segments"),
        "lat": coords[0],
        "lng": coords[1],
        **{k: v for k, v in route.items() if k not in ("duration_sec", "distance_m", "polyline", "polyline_segments")},
    }

    if compare_modes:
        item["per_mode"] = await _compute_per_mode_points(points, mode, city)

    return item


async def _route_points(
    points: List[Tuple[float, float]],
    mode: str,
    city: Optional[str],
) -> Optional[Dict[str, Any]]:
    """对有序点列逐段调用 _direction 并聚合（多段通勤）。

    points: [(lat,lng), ...] 至少 2 个点。返回聚合后的标准化路线字典。
    """
    legs: List[Dict[str, Any]] = []
    for i in range(len(points) - 1):
        origin_d = {"lat": points[i][0], "lng": points[i][1]}
        try:
            leg = await _direction(origin_d, points[i + 1], mode, city)
        except Exception as exc:
            raise RuntimeError(f"第 {i + 1} 段路径规划失败：{exc}")
        if leg is None:
            return None
        legs.append(leg)
    return _aggregate_legs(legs)


def _aggregate_legs(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """聚合多段路线：累加耗时/距离，拼接几何与行程段。"""
    total_dur = 0
    total_dist = 0
    seg_polys: List[str] = []
    flat_poly: List[str] = []
    steps: List[Dict[str, Any]] = []
    transfers = 0
    has_subway = False
    transit_lines: List[str] = []
    for l in legs:
        total_dur += int(l.get("duration_sec") or 0)
        total_dist += int(l.get("distance_m") or 0)
        if l.get("polyline_segments"):
            seg_polys.extend(l["polyline_segments"])
        elif l.get("polyline"):
            seg_polys.append(l["polyline"])
        if l.get("polyline"):
            flat_poly.append(l["polyline"])
        if l.get("steps_detail"):
            steps.extend(l["steps_detail"])
        transfers += int(l.get("transfers") or 0)
        if l.get("has_subway"):
            has_subway = True
        if l.get("transit_lines"):
            transit_lines.extend(l["transit_lines"])
    return {
        "duration_sec": total_dur,
        "distance_m": total_dist,
        "transfers": transfers or None,
        "polyline": ";".join(flat_poly) if flat_poly else None,
        "polyline_segments": seg_polys if seg_polys else None,
        "has_subway": has_subway or None,
        "transit_lines": transit_lines or None,
        "steps_detail": steps or None,
    }


async def _compute_per_mode(
    origin: Dict[str, float],
    coords: Tuple[float, float],
    chosen_mode: str,
    city: Optional[str],
) -> Dict[str, Any]:
    """计算全部 4 种出行方式的耗时/距离，用于横向对比。

    选定方式走缓存（_direction 已缓存），其余方式按需实时计算；
    单方式失败不影响整体，记入 error。
    """
    points = [(origin["lat"], origin["lng"]), coords]
    return await _compute_per_mode_points(points, chosen_mode, city)


async def _compute_per_mode_points(
    points: List[Tuple[float, float]],
    chosen_mode: str,
    city: Optional[str],
) -> Dict[str, Any]:
    """与 _compute_per_mode 相同，但支持多段点列（含途经点）。"""
    # transit 需要城市：缺省时由起点反查一次
    transit_city = city
    if "transit" in VALID_MODES and not transit_city:
        transit_city = await _reverse_geocode_city(points[0][0], points[0][1])

    per: Dict[str, Any] = {}
    for m in VALID_MODES:
        try:
            r = await _route_points(points, m, transit_city if m == "transit" else None)
            if r is None:
                per[m] = {"duration_sec": None, "distance_m": None}
            else:
                per[m] = {
                    "duration_sec": r["duration_sec"],
                    "distance_m": r["distance_m"],
                }
        except Exception as exc:
            logger.warning("per_mode %s failed: %s", m, exc)
            per[m] = {"error": str(exc)}
    return per


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

    parsed = await _parse_route(data, mode, city)
    if parsed is not None:
        _ROUTE_CACHE[cache_key] = parsed
        _ROUTE_CACHE_TS[cache_key] = time.time()
    return parsed


async def _fetch_busline_polyline(
    city: Optional[str], line_name: str
) -> Optional[str]:
    """调高德 v3/bus/linename 获取某条公交/地铁线路的完整 polyline。

    用于补全 transit 路线中缺失的轨道几何：默认 integrated 响应里只有步行段带
    polyline，公交/地铁段无坐标。这里按线路名查线路详情，拿到整条线几何后拼接，
    得到接近真实的轨道线（方向取首条，为近似）。

    注意：/v3/bus/busline 在本 key 下返回 SERVICE_NOT_AVAILABLE，须用 linename。
    """
    if not city or not line_name:
        return None
    # 去掉方向括号（如 "269路(江西农大--南昌西站)" -> "269路"），提高匹配度
    query_name = line_name.split("(")[0].strip()
    if not query_name:
        query_name = line_name
    cache_key = f"{city}:{query_name}"
    if cache_key in _BUSLINE_CACHE and (
        time.time() - _BUSLINE_CACHE_TS.get(cache_key, 0) < _BUSLINE_TTL_S
    ):
        return _BUSLINE_CACHE[cache_key]
    api_key = settings.amap_maps_api_key
    if not api_key:
        return None
    params = {
        "key": api_key,
        "city": city,
        "keywords": query_name,
        "extensions": "all",
        "output": "JSON",
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                f"{AMAP_DIRECTION_BASE}/v3/bus/linename", params=params
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("busline query failed for %s: %s", query_name, exc)
        return None
    if data.get("status") != "1":
        return None
    buslines = data.get("buslines") or []
    poly: Optional[str] = buslines[0].get("polyline") if buslines else None
    _BUSLINE_CACHE[cache_key] = poly
    _BUSLINE_CACHE_TS[cache_key] = time.time()
    return poly


async def _parse_route(
    data: Dict[str, Any], mode: str, city: Optional[str] = None
) -> Optional[Dict[str, Any]]:
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

        # ---- 拼接路线几何：步行段 + 各公交/地铁段的完整线路 polyline ----
        # 默认 integrated 响应里只有步行段带 polyline，公交/地铁段无坐标；
        # 这里对每段 busline 调线路详情补全整条轨道线，得到接近真实的路线形态。
        # route_segments 保留每段独立（不拼接），前端逐段绘制可避免步行段末端
        # 与公交/地铁线起点之间的「跨城连线」（地铁整条线很长，拼接会很突兀）。
        route_segments: List[str] = []
        for seg in segments:
            walk = seg.get("walking") or {}
            for step in walk.get("steps", []):
                p = step.get("polyline")
                if p:
                    route_segments.append(p)
            bus_info = seg.get("bus") or {}
            for bl in bus_info.get("buslines", []):
                line_name = bl.get("name", "")
                if line_name:
                    bl_poly = await _fetch_busline_polyline(city, line_name)
                    if bl_poly:
                        route_segments.append(bl_poly)
        polyline = ";".join(route_segments) if route_segments else None
        polyline_segments = route_segments if route_segments else None

        result = {
            "duration_sec": duration,
            "distance_m": distance,
            "transfers": transfers,
            "polyline": polyline,
            "polyline_segments": polyline_segments,
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


# ---------------------------------------------------------------------------
# 周边 POI 推荐（高德 v3/place/around）
# ---------------------------------------------------------------------------

async def search_nearby_pois(
    lat: float,
    lng: float,
    radius: int = 1000,
    keywords: Optional[str] = None,
    types: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """给定坐标，返回周边 POI（餐饮/地铁站/便利店等）。

    Returns:
        [{"name", "address", "category", "distance", "lat", "lng"}, ...]
    """
    api_key = settings.amap_maps_api_key
    if not api_key:
        return []

    params: Dict[str, Any] = {
        "key": api_key,
        "location": f"{lng},{lat}",
        "radius": radius,
        "offset": min(limit, 25),
        "page": 1,
        "extensions": "base",
        "output": "JSON",
        "sortrule": "weight",
    }
    if keywords:
        params["keywords"] = keywords
    if types:
        params["types"] = types

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{AMAP_DIRECTION_BASE}/v3/place/around", params=params
        )
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "1":
        return []

    pois: List[Dict[str, Any]] = []
    for p in data.get("pois", []):
        loc = p.get("location")
        if not loc:
            continue
        loc_parts = str(loc).split(",")
        if len(loc_parts) != 2:
            continue
        try:
            plng, plat = float(loc_parts[0]), float(loc_parts[1])
        except (ValueError, IndexError):
            continue
        pois.append({
            "name": p.get("name", ""),
            "address": p.get("address") or "",
            "category": p.get("type") or "",
            "distance": int(float(p.get("distance") or 0)),
            "lat": plat,
            "lng": plng,
        })
        if len(pois) >= limit:
            break
    return pois
