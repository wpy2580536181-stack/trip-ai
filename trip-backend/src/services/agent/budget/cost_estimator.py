"""费用估算器：真实 avg_cost 优先，城市消费档位兜底（纯函数，无 LLM/IO/状态）。

CITY_TIER 推导来源：trip_db.spots 表 avg_cost 有值样本（532/30803 条，中位数 80/Q1 60/Q3 150），
按城市中位数分档：≥100 元为 high（北京/上海/广州/深圳/武汉/厦门/宁波/重庆/哈尔滨/大连/长沙/郑州/福州），
60-99 为 medium（南京/青岛/杭州/苏州/西安/贵阳/昆明等），其余为 low。
"""

from src.services.agent.schemas import CostSource

CITY_TIER = {
    "high":   {"attraction": 120, "food_per": 100, "hotel_night": 400},
    "medium": {"attraction": 80,  "food_per": 80,  "hotel_night": 250},
    "low":    {"attraction": 50,  "food_per": 60,  "hotel_night": 150},
}

HIGH_CITIES = [
    "北京", "上海", "广州", "深圳", "武汉", "厦门", "宁波",
    "重庆", "哈尔滨", "大连", "长沙", "郑州", "福州",
]
MEDIUM_CITIES = [
    "南京", "青岛", "杭州", "苏州", "西安", "贵阳", "昆明", "桂林",
    "合肥", "太原", "石家庄", "乌鲁木齐", "天津", "成都", "济南",
]

_HIGH_SET = frozenset(HIGH_CITIES)
_MEDIUM_SET = frozenset(MEDIUM_CITIES)


def get_city_tier(city: str) -> str:
    """按城市名返回档位。城市名含"市"后缀需去除匹配；未知城市返回 low。"""
    if not city:
        return "low"
    name = city[:-1] if city.endswith("市") else city
    if name in _HIGH_SET:
        return "high"
    if name in _MEDIUM_SET:
        return "medium"
    return "low"


def estimate_cost(spot: dict, city_tier: str, category: str = "attraction") -> tuple[int, CostSource]:
    """返回 (金额, 来源)。avg_cost 真值>0 → (真值, RAG)；否则 (档位默认, ESTIMATE)。"""
    avg_cost = spot.get("avg_cost")
    if avg_cost is not None and float(avg_cost) > 0:
        return int(avg_cost), CostSource.RAG
    tier = city_tier if city_tier in CITY_TIER else "low"
    return CITY_TIER[tier][category], CostSource.ESTIMATE


def enrich_search_results(results: list[dict], city_tier: str, category: str = "attraction") -> list[dict]:
    """每条附加 avg_cost（int 或 None）与 cost_source（字符串值），不改动原 dict（返回新 dict 列表）。"""
    enriched = []
    for item in results:
        amount, source = estimate_cost(item, city_tier, category)
        new_item = dict(item)
        new_item["avg_cost"] = amount
        new_item["cost_source"] = source.value
        enriched.append(new_item)
    return enriched
