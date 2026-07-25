"""Calculate Distance 工具模块。

计算两个城市之间的交通距离、时间和费用。
迁移自 Node.js 版本的 tools/calculateDistance.ts。

路网策略（2026-07-17 升级）：
- car 模式：不再用 Haversine 直线估算，而是复用 commute_service 的真实驾车路网
  （高德 v5 Direction），拿到真实里程与耗时；公里/小时为真实路网值。
- train / flight 模式：铁路与航班暂无公开路网 API，保留直线距离 + 经验估算，
  并在输出中标注「估算」。
- 任一真实路网调用失败（无 Key / 网络异常）时，自动回退到 Haversine 估算，
  保证工具始终可用（被 with_resilience 再包一层）。
"""

import logging
from typing import Optional, Tuple

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.services.agent.resilience import with_resilience
from src.services.geocode_service import geocode_spot


# 主要城市的经纬度坐标
CITY_COORDS = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "成都": (30.5728, 104.0668),
    "杭州": (30.2741, 120.1551),
    "武汉": (30.5928, 114.3055),
    "西安": (34.3416, 108.9398),
    "重庆": (29.4316, 106.9123),
    "南京": (32.0603, 118.7969),
    "天津": (39.3434, 117.3616),
    "长沙": (28.2282, 112.9388),
    "苏州": (31.2990, 120.5853),
    "厦门": (24.4798, 118.0894),
    "青岛": (36.0671, 120.3826),
    "大连": (38.9140, 121.6147),
    "昆明": (25.0389, 102.7183),
    "三亚": (18.2528, 109.5120),
    "哈尔滨": (45.8038, 126.5350),
    "桂林": (25.2736, 110.2900),
    "拉萨": (29.6500, 91.1000),
    "乌鲁木齐": (43.8256, 87.6168),
    "贵阳": (26.6470, 106.6302),
    "南宁": (22.8170, 108.3665),
    "南昌": (28.6829, 115.8582),
    "福州": (26.0745, 119.2965),
    "合肥": (31.8206, 117.2272),
    "郑州": (34.7466, 113.6253),
    "济南": (36.6512, 116.9972),
    "太原": (37.8706, 112.5489),
    "兰州": (36.0611, 103.8343),
}


class CalculateDistanceInput(BaseModel):
    """Calculate Distance 工具输入参数。"""

    from_city: str = Field(description="出发城市名")
    to_city: str = Field(description="目的地城市名")
    mode: Optional[str] = Field(
        None,
        description="交通方式：train/car/flight，默认 flight",
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """使用 Haversine 公式计算两点之间的直线距离（公里）。仅作回退用。"""
    import math

    R = 6371  # 地球半径（公里）

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def _estimate_travel(km: float, mode: str) -> dict:
    """估算交通时间和费用（train / flight 模式，或 car 真实路网失败的回退）。"""
    if mode == "train":
        return {
            "time": f"{round(km / 300)} 小时",
            "cost_min": round(km * 0.3),
            "cost_max": round(km * 0.8),
        }
    elif mode == "car":
        return {
            "time": f"{round(km / 80)} 小时",
            "cost_min": round(km * 0.6),
            "cost_max": round(km * 1.2),
        }
    else:  # flight
        return {
            "time": f"{round(km / 800) + 1} 小时（含值机候机）",
            "cost_min": round(km * 0.5),
            "cost_max": round(km * 1.5),
        }


async def _resolve_city_coord(city: str) -> Optional[Tuple[float, float]]:
    """解析城市坐标为 (lat, lng)：先查内置表，再地理编码兜底。"""
    c = CITY_COORDS.get(city)
    if c:
        return (float(c[0]), float(c[1]))
    try:
        geo = await geocode_spot(city, city)
        if geo:
            return (float(geo["lat"]), float(geo["lng"]))
    except Exception as exc:
        logger.warning("geocode city %s failed: %s", city, exc)
    return None


logger = logging.getLogger(__name__)


@tool(args_schema=CalculateDistanceInput)
async def calculate_distance_tool(
    from_city: str,
    to_city: str,
    mode: Optional[str] = "flight",
) -> str:
    """计算两个城市之间的交通距离、时间和大致费用。

    当用户询问"A到B多远"、"怎么去"、"交通时间"时使用。
    - car 模式返回高德真实驾车路网里程与耗时；
    - train / flight 模式为直线距离 + 经验估算（标注「估算」）。

    Args:
        from_city: 出发城市名
        to_city: 目的地城市名
        mode: 交通方式（可选，默认 flight）

    Returns:
        距离信息字符串
    """
    mode = (mode or "flight").lower()
    c1 = await _resolve_city_coord(from_city)
    c2 = await _resolve_city_coord(to_city)

    if not c1 or not c2:
        unknown = []
        if not c1:
            unknown.append(from_city)
        if not c2:
            unknown.append(to_city)
        available = list(CITY_COORDS.keys())[:15]
        return (
            f"暂不支持城市 {', '.join(unknown)} 的距离查询。"
            f"可用的城市：{'、'.join(available)}等。"
        )

    mode_cn = "高铁" if mode == "train" else ("自驾" if mode == "car" else "飞机")

    # car 模式：走真实驾车路网（高德 v5 Direction）
    if mode == "car":
        try:
            from src.services.commute_service import compute_road_distance

            road = await compute_road_distance(
                {"lat": c1[0], "lng": c1[1]},
                {"lat": c2[0], "lng": c2[1]},
                "driving",
            )
            if road:
                km = road["distance_m"] / 1000.0
                hours = road["duration_sec"] / 3600.0
                # 费用估算：油费/电费 + 高速过路费（约 0.45 元/km）
                fuel = round(km * 0.6)
                toll = round(km * 0.45)
                return "\n".join([
                    f"从 {from_city} 到 {to_city}（驾车·真实路网）",
                    f"驾车距离：{km:.0f} 公里",
                    f"驾车时间：约 {hours:.1f} 小时",
                    f"预估费用：油费/电费约 {fuel} 元，高速过路费约 {toll} 元",
                ])
        except Exception as exc:
            logger.warning("real road distance failed, fallback: %s", exc)
            # 落到下面的 haversine 估算

    # train / flight / car 回退：直线距离 + 经验估算
    km = _haversine_km(c1[0], c1[1], c2[0], c2[1])
    est = _estimate_travel(km, mode)
    note = "（直线距离估算）" if mode != "flight" else "（含值机候机估算）"

    return "\n".join([
        f"从 {from_city} 到 {to_city}{note}",
        f"直线距离：{round(km)} 公里",
        f"交通方式：{mode_cn}",
        f"预估时间：{est['time']}",
        f"预估费用：{est['cost_min']}~{est['cost_max']} 元",
    ])


# 应用韧性包装（超时 + 重试 + 熔断 + 降级）
calculate_distance_tool = with_resilience(
    calculate_distance_tool,
    timeout=5.0,
    retries=1,
    fallback="距离计算暂时不可用。",
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=30.0,
)
