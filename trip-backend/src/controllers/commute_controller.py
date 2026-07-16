"""Commute（最短通勤择优）控制器。

路由前缀 /commute，挂载到 /api 下，因此完整路径为 /api/commute/optimal。
响应沿用项目通用 Format B：{code, data, message, error}。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.schemas.commute import CommuteRequest, CommuteResponse
from src.services.commute_service import compute_optimal_commute, search_input_tips, search_nearby_pois
from src.services.geocode_service import geocode_spot

router = APIRouter(prefix="/commute", tags=["Commute"])


# ---------------------------------------------------------------------------
# 输入联想（高德 inputtips）
# ---------------------------------------------------------------------------

class InputTipsItem(BaseModel):
    """单条联想结果"""
    name: str = Field(..., description="名称")
    address: Optional[str] = Field(default=None, description="地址")
    district: Optional[str] = Field(default=None, description="区县")
    lat: Optional[float] = Field(default=None, description="纬度（有坐标时）")
    lng: Optional[float] = Field(default=None, description="经度（有坐标时）")


class InputTipsResponse(BaseModel):
    """联想接口响应"""
    tips: List[InputTipsItem]


class GeocodeResponse(BaseModel):
    """地理编码结果"""
    lat: Optional[float] = Field(default=None, description="纬度")
    lng: Optional[float] = Field(default=None, description="经度")
    found: bool = Field(default=False, description="是否命中坐标")


@router.get("/geocode", response_model=GeocodeResponse)
async def geocode(
    address: str = Query(..., min_length=1, max_length=100, description="地址或地点名称"),
    city: Optional[str] = Query(None, description="城市名（可选，提高精度）"),
):
    """地址地理编码（调高德 v3/geocode/geo），返回经纬度。

    前端在「添加候选」时调用，使候选点立即出现在地图上；编码失败也不阻断，
    计算阶段后端会再次尝试。
    """
    try:
        coords = await geocode_spot(address, city or "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"地理编码异常：{exc}")
    if coords:
        return {"lat": coords["lat"], "lng": coords["lng"], "found": True}
    return {"found": False}


@router.get("/inputtips", response_model=InputTipsResponse)
async def inputtips(
    keywords: str = Query(..., min_length=1, max_length=50, description="搜索关键词"),
    city: Optional[str] = Query(None, description="城市名（可选，限制结果范围）"),
):
    """地址输入联想（调高德 v3 /v3/assistant/inputtips）。"""
    if not keywords.strip():
        raise HTTPException(status_code=400, detail="keywords 不能为空")
    try:
        items = await search_input_tips(keywords, city)
        return {"tips": items}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"联想服务异常：{exc}")


class NearbyResponse(BaseModel):
    """周边 POI 推荐响应"""
    pois: List[Dict[str, Any]]


@router.get("/nearby", response_model=NearbyResponse)
async def nearby(
    lat: float = Query(..., description="中心纬度"),
    lng: float = Query(..., description="中心经度"),
    radius: int = Query(1000, ge=100, le=5000, description="搜索半径（米）"),
    keywords: Optional[str] = Query(None, description="关键词（如：地铁站 / 咖啡）"),
    types: Optional[str] = Query(None, description="POI 分类编码（高德 category code）"),
):
    """周边 POI 推荐（调高德 v3/place/around）。用于展示候选地附近的地标。"""
    try:
        pois = await search_nearby_pois(lat, lng, radius, keywords, types)
        return {"pois": pois}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"周边搜索异常：{exc}")


@router.post("/optimal")
async def optimal(req: CommuteRequest):
    """计算从当前位置到各候选目的地的最短通勤。

    - 单程：仅算 当前 -> 候选 的耗时（按产品决策）。
    - 并行计算所有候选，按耗时升序返回，并标记 recommended（最短者）。
    - 单个候选失败不中断，计入 errors。
    """
    try:
        result = await compute_optimal_commute(
            req.origin.model_dump(),
            [d.model_dump() for d in req.destinations],
            req.mode,
            req.city,
            req.compare_modes,
            [w.model_dump() for w in req.waypoints] if req.waypoints else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "code": 0,
        "data": CommuteResponse(**result).model_dump(),
        "message": "ok",
    }
