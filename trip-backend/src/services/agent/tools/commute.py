"""Commute 工具模块。

把最短通勤择优服务（src.services.commute_service）包装成 agent 工具，
供 route-optimize skill 在 L3 指令驱动下调用。

迁移自 Node.js 版本的 tools/commute.ts 思路，复用已有 commute_service 的真实路网能力。
"""

import json
import logging
from typing import List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.services.agent.resilience import with_resilience

logger = logging.getLogger(__name__)


class LocationInput(BaseModel):
    """一个地点：可带坐标，也可只带名称 + 城市由服务做地理编码。"""

    name: Optional[str] = Field(None, description="地点名称，如「家」「公司」「人民广场」")
    lat: Optional[float] = Field(None, description="纬度（若已知坐标）")
    lng: Optional[float] = Field(None, description="经度（若已知坐标）")
    city: Optional[str] = Field(None, description="所在城市名，地理编码需要")
    address: Optional[str] = Field(None, description="详细地址，辅助地理编码")


class ComputeCommuteInput(BaseModel):
    """计算最优通勤的输入。"""

    origin: LocationInput = Field(description="起点（家 / 当前位置）")
    destinations: List[LocationInput] = Field(description="候选终点列表，可多个用于择优")
    mode: str = Field(
        description="出行方式：driving 驾车 / walking 步行 / transit 公交 / cycling 骑行"
    )
    city: Optional[str] = Field(None, description="起点城市（公交 transit 规划必填）")
    compare_modes: bool = Field(False, description="为 true 时额外横向对比 4 种出行方式耗时")


def _loc_to_dict(loc: LocationInput) -> dict:
    """LocationInput -> commute_service 接受的 dict（只保留已提供的字段）。"""
    d: dict = {}
    if loc.name is not None:
        d["name"] = loc.name
    if loc.lat is not None:
        d["lat"] = loc.lat
    if loc.lng is not None:
        d["lng"] = loc.lng
    if loc.city is not None:
        d["city"] = loc.city
    if loc.address is not None:
        d["address"] = loc.address
    return d


def _trim_item(it: dict) -> dict:
    """去掉地图几何（polyline）等前端专用字段，保留 LLM 组织回答所需的数据。"""
    d = {
        "name": it.get("name"),
        "id": it.get("id"),
        "duration_sec": it.get("duration_sec"),
        "distance_m": it.get("distance_m"),
        "transfers": it.get("transfers"),
        "lat": it.get("lat"),
        "lng": it.get("lng"),
        "per_mode": it.get("per_mode"),
        "steps_detail": it.get("steps_detail"),
    }
    return {k: v for k, v in d.items() if v is not None}


def _format_commute(result: dict) -> str:
    rec = result.get("recommended")
    out = {
        "mode": result.get("mode"),
        "recommended": _trim_item(rec) if rec else None,
        "candidates": [_trim_item(r) for r in result.get("results", [])],
        "errors": result.get("errors", []),
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


@tool(args_schema=ComputeCommuteInput)
async def compute_optimal_commute_tool(
    origin: LocationInput,
    destinations: List[LocationInput],
    mode: str,
    city: Optional[str] = None,
    compare_modes: bool = False,
) -> str:
    """计算最短通勤并择优推荐。

    给定起点与若干候选终点（可带坐标，也可只给名称 + 城市由服务自动地理编码），
    并行调用高德真实路网，按耗时升序排序并标记最短者为推荐。支持驾车 / 步行 / 公交 / 骑行。
    当用户问「从家到公司怎么走最快」「哪条路线通勤最短」「推荐最优通勤路线」时使用。

    Returns:
        结构化 JSON：推荐路线（含逐步行程 steps_detail、换乘数）、所有候选耗时 / 距离、错误项。
    """
    from ...commute_service import compute_optimal_commute

    try:
        result = await compute_optimal_commute(
            origin=_loc_to_dict(origin),
            destinations=[_loc_to_dict(d) for d in destinations],
            mode=mode,
            city=city,
            compare_modes=compare_modes,
        )
        return _format_commute(result)
    except Exception as e:
        return json.dumps({"error": f"路线规划失败：{e}"}, ensure_ascii=False)


# 应用韧性包装（超时 + 重试 + 熔断 + 降级）
compute_optimal_commute_tool = with_resilience(
    compute_optimal_commute_tool,
    timeout=20.0,  # 多候选并行，给足超时
    retries=1,
    fallback=json.dumps({"error": "通勤路线规划暂时不可用，请稍后再试。"}),
    circuit_breaker_failure_threshold=5,   # 连续失败 5 次熔断（下游为高德真实路网）
    circuit_breaker_recovery_timeout=30.0,  # 30s 后进入 Half-Open 试探
)


class SearchCommuteTipsInput(BaseModel):
    """输入提示（地理编码辅助）的输入。"""

    keywords: str = Field(description="要搜索的地点关键词，如「人民广场」「公司」")
    city: Optional[str] = Field(None, description="城市名，缩小联想范围")
    limit: int = Field(5, description="返回条数")


@tool(args_schema=SearchCommuteTipsInput)
async def search_commute_tips_tool(
    keywords: str, city: Optional[str] = None, limit: int = 5
) -> str:
    """根据关键词联想地点并返回候选坐标（地址解析 / 地理编码辅助）。

    当用户给出的起点或终点只是名称（如「家」「公司」「人民广场」）而没有坐标时，
    先调用本工具拿到候选地点的 lat / lng，再传给 compute_optimal_commute。
    """
    from ...commute_service import search_input_tips

    try:
        tips = await search_input_tips(keywords, city, limit)
        return json.dumps(tips, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"地点联想失败：{e}"}, ensure_ascii=False)


search_commute_tips_tool = with_resilience(
    search_commute_tips_tool,
    timeout=8.0,
    retries=1,
    fallback=json.dumps({"error": "地点联想暂时不可用。"}),
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=30.0,
)


class SearchNearbyCommutePoisInput(BaseModel):
    """周边 POI 查询的输入。"""

    lat: float = Field(description="中心点纬度")
    lng: float = Field(description="中心点经度")
    radius: int = Field(1000, description="搜索半径（米）")
    keywords: Optional[str] = Field(None, description="关键词，如「地铁站」「咖啡」")
    types: Optional[str] = Field(None, description="POI 类型编码")
    limit: int = Field(15, description="返回条数")


@tool(args_schema=SearchNearbyCommutePoisInput)
async def search_nearby_commute_pois_tool(
    lat: float,
    lng: float,
    radius: int = 1000,
    keywords: Optional[str] = None,
    types: Optional[str] = None,
    limit: int = 15,
) -> str:
    """查询某坐标周边的 POI（地铁站 / 餐饮 / 便利店等），用于通勤周边推荐。"""
    from ...commute_service import search_nearby_pois

    try:
        pois = await search_nearby_pois(lat, lng, radius, keywords, types, limit)
        return json.dumps(pois, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"周边 POI 查询失败：{e}"}, ensure_ascii=False)


search_nearby_commute_pois_tool = with_resilience(
    search_nearby_commute_pois_tool,
    timeout=8.0,
    retries=1,
    fallback=json.dumps({"error": "周边 POI 查询暂时不可用。"}),
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=30.0,
)
