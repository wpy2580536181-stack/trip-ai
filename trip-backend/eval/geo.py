"""
城市坐标 + 周边城市判定（100km 直线距离）

用 Haversine 公式算两点间球面距离。
100km 是一个比较保守的"周边"——城市群内 1.5h 高铁可达范围。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CityCoord:
    name: str
    lat: float
    lng: float


# fmt: off
CITY_COORDS: list[CityCoord] = [
    # 一线
    CityCoord("北京", 39.9042, 116.4074),
    CityCoord("上海", 31.2304, 121.4737),
    CityCoord("广州", 23.1291, 113.2644),
    CityCoord("深圳", 22.5431, 114.0579),
    # 强二线 / 旅游热门
    CityCoord("成都", 30.5728, 104.0668),
    CityCoord("重庆", 29.5630, 106.5516),
    CityCoord("杭州", 30.2741, 120.1551),
    CityCoord("西安", 34.3416, 108.9398),
    CityCoord("南京", 32.0603, 118.7969),
    CityCoord("苏州", 31.2989, 120.5853),
    CityCoord("天津", 39.3434, 117.3616),
    CityCoord("武汉", 30.5928, 114.3055),
    CityCoord("长沙", 28.2282, 112.9388),
    CityCoord("青岛", 36.0671, 120.3826),
    CityCoord("厦门", 24.4798, 118.0894),
    CityCoord("大连", 38.9140, 121.6147),
    CityCoord("昆明", 25.0389, 102.7183),
    CityCoord("丽江", 26.8721, 100.2330),
    CityCoord("大理", 25.6065, 100.2676),
    CityCoord("三亚", 18.2528, 109.5119),
    CityCoord("桂林", 25.2736, 110.2907),
    CityCoord("张家界", 29.1170, 110.4791),
    CityCoord("黄山", 29.7147, 118.3376),
    CityCoord("拉萨", 29.6500, 91.1700),
    CityCoord("敦煌", 40.1421, 94.6612),
    # 城市群周边（100km 内常见旅游目的地）
    CityCoord("都江堰", 30.9912, 103.6190),   # 成都西北 ~50km
    CityCoord("青城山", 30.9000, 103.5667),   # 成都西 ~60km
    CityCoord("乐山", 29.5521, 103.7660),     # 成都南 ~130km
    CityCoord("峨眉山", 29.5167, 103.4833),   # 成都南 ~140km
    CityCoord("昆山", 31.3819, 120.9786),     # 上海西 ~50km
    CityCoord("嘉兴", 30.7522, 120.7506),     # 上海南 ~85km
    CityCoord("无锡", 31.4912, 120.3119),     # 上海西 ~100km
    CityCoord("绍兴", 30.0023, 120.5810),     # 杭州东 ~60km
    CityCoord("乌镇", 30.7461, 120.4943),     # 杭州北 ~80km
    CityCoord("千岛湖", 29.6058, 119.0217),   # 杭州西 ~120km
    CityCoord("西塘", 30.9303, 120.8916),     # 上海西 ~85km
    CityCoord("秦皇岛", 39.9354, 119.6005),   # 北京东 ~280km
    CityCoord("承德", 40.9519, 117.9634),     # 北京东北 ~200km
    CityCoord("平遥", 37.1894, 112.1742),     # 太原南
    CityCoord("华山", 34.4833, 110.0833),     # 西安东 ~120km
    CityCoord("武当山", 32.4000, 111.0000),   # 武汉西北 ~400km
    CityCoord("凤凰", 27.9483, 109.5992),     # 长沙西
    CityCoord("北戴河", 39.8300, 119.4900),   # 北京东
    CityCoord("婺源", 29.2485, 117.8612),     # 景德镇
    CityCoord("宏村", 29.9110, 117.9833),     # 黄山
    # 国际
    CityCoord("东京", 35.6762, 139.6503),
    CityCoord("京都", 35.0116, 135.7681),
    CityCoord("大阪", 34.6937, 135.5023),
    CityCoord("首尔", 37.5665, 126.9780),
    CityCoord("曼谷", 13.7563, 100.5018),
    CityCoord("清迈", 18.7883, 98.9853),
    CityCoord("巴黎", 48.8566, 2.3522),
    CityCoord("伦敦", 51.5074, -0.1278),
    CityCoord("纽约", 40.7128, -74.0060),
    CityCoord("罗马", 41.9028, 12.4964),
    CityCoord("巴塞罗那", 41.3851, 2.1734),
    CityCoord("香港", 22.3193, 114.1694),
    CityCoord("澳门", 22.1987, 113.5439),
    CityCoord("台北", 25.0330, 121.5654),
    CityCoord("镰仓", 35.3197, 139.5466),     # 东京南 ~50km
    CityCoord("横滨", 35.4437, 139.6380),     # 东京南 ~30km
    CityCoord("奈良", 34.6851, 135.8048),     # 京都西 ~30km
    CityCoord("神户", 34.6901, 135.1955),     # 大阪西 ~30km
    CityCoord("日惹", -7.7956, 110.3695),
    CityCoord("巴厘岛", -8.4095, 115.1889),
    CityCoord("普吉岛", 7.8804, 98.3923),
]
# fmt: on

EARTH_RADIUS_KM: float = 6371.0
NEARBY_RADIUS_KM: float = 100.0

_COORD_MAP: dict[str, CityCoord] = {c.name: c for c in CITY_COORDS}


def _to_rad(deg: float) -> float:
    return deg * math.pi / 180.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great-circle distance between two points in km."""
    d_lat = _to_rad(lat2 - lat1)
    d_lng = _to_rad(lon2 - lon1)
    a_lat = _to_rad(lat1)
    b_lat = _to_rad(lat2)
    h = math.sin(d_lat / 2) ** 2 + math.cos(a_lat) * math.cos(b_lat) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _haversine_km(a: CityCoord, b: CityCoord) -> float:
    return haversine_distance(a.lat, a.lng, b.lat, b.lng)


def city_distance_km(a: str, b: str) -> float | None:
    """计算两个城市之间的直线距离 km；任一城市未登记返回 None。"""
    ca = _COORD_MAP.get(a)
    cb = _COORD_MAP.get(b)
    if ca is None or cb is None:
        return None
    return _haversine_km(ca, cb)


def is_within_radius(city: str, lat: float, lon: float, radius_km: float = NEARBY_RADIUS_KM) -> bool:
    """判断 (lat, lon) 是否在 city 的 radius_km 范围内。"""
    coord = _COORD_MAP.get(city)
    if coord is None:
        return False
    return haversine_distance(coord.lat, coord.lng, lat, lon) <= radius_km


def is_city_or_nearby(poi_city: str, expected_city: str) -> bool:
    """判断 poi_city 是否在 expected_city 周边（100km 内）或同名。

    - 任一未登记 → 仅做严格相等
    """
    if poi_city == expected_city:
        return True
    dist = city_distance_km(poi_city, expected_city)
    if dist is None:
        return False
    return dist <= NEARBY_RADIUS_KM


def list_nearby(city: str) -> list[str]:
    """列出某城市 100km 内的所有已知城市（调试用）。"""
    c = _COORD_MAP.get(city)
    if c is None:
        return []
    return [
        other.name
        for other in CITY_COORDS
        if other.name != city and _haversine_km(c, other) <= NEARBY_RADIUS_KM
    ]
