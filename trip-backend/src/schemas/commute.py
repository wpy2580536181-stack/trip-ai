"""Commute（最短通勤择优）请求/响应模型"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Coord(BaseModel):
    """经纬度坐标"""

    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")


class Candidate(BaseModel):
    """候选目的地

    坐标解析优先级：
    1. 直接提供 lat/lng 则使用；
    2. 否则用 address 或 name + city 走地理编码得到坐标。
    """

    id: Optional[str] = Field(default=None, description="业务 ID（如知识库 spot id）")
    name: str = Field(..., description="目的地名称（用于展示与地理编码回退）")
    lat: Optional[float] = Field(default=None, description="纬度（有则直接用）")
    lng: Optional[float] = Field(default=None, description="经度（有则直接用）")
    city: Optional[str] = Field(default=None, description="城市（地理编码/公交规划所需）")
    address: Optional[str] = Field(default=None, description="详细地址（地理编码回退）")


class CommuteRequest(BaseModel):
    """POST /api/commute/optimal 请求体"""

    origin: Coord = Field(..., description="当前位置坐标")
    destinations: List[Candidate] = Field(
        ..., min_length=1, max_length=20, description="候选目的地列表"
    )
    mode: str = Field(
        default="driving",
        description="出行方式：driving / walking / transit / cycling",
    )
    city: Optional[str] = Field(
        default=None, description="当前城市（transit 公交规划必填，可缺省时回退）"
    )
    waypoints: List[Candidate] = Field(
        default_factory=list,
        description="途经点（多段通勤）：起点到候选目的地之间依次经过的点，累加各段路程",
    )
    compare_modes: bool = Field(
        default=False,
        description="为 true 时，除选定方式外额外计算其余 3 种方式，返回 per_mode 横向对比",
    )


class TransitStepDetail(BaseModel):
    """公交逐步行程中的一段"""

    type: str = Field(..., description="walking / subway / bus / transfer_walk")
    label: str = Field(..., description="显示名称，如 '地铁1号线' 或 '步行'")
    distance_m: Optional[int] = Field(default=None, description="该段距离（米）")
    duration_sec: Optional[int] = Field(default=None, description="该段耗时（秒）")
    departure: Optional[str] = Field(default=None, description="出发站（公交/地铁）")
    arrival: Optional[str] = Field(default=None, description="到达站（公交/地铁）")
    via_stops: Optional[int] = Field(default=None, description="途经站数")


class CommuteResultItem(BaseModel):
    """单个候选的计算结果"""

    id: Optional[str] = None
    name: str
    duration_sec: int = Field(..., description="通勤耗时（秒）")
    distance_m: int = Field(..., description="通勤距离（米）")
    transfers: Optional[int] = Field(default=None, description="换乘次数（仅公交）")
    polyline: Optional[str] = Field(default=None, description="路线几何（明文 lng,lat;... 或步行段近似）")
    polyline_segments: Optional[List[str]] = Field(
        default=None,
        description="公交路线分段几何（每段独立），用于逐段绘制避免跨城连线",
    )
    lat: Optional[float] = Field(default=None, description="目的地纬度（用于导航深链）")
    lng: Optional[float] = Field(default=None, description="目的地经度（用于导航深链）")
    has_subway: Optional[bool] = Field(default=None, description="是否包含地铁（仅公交）")
    transit_lines: Optional[List[str]] = Field(default=None, description="公交/地铁线路名称列表（仅公交）")
    steps_detail: Optional[List[TransitStepDetail]] = Field(
        default=None, description="逐步行程详情（仅公交）"
    )
    per_mode: Optional[Dict[str, Any]] = Field(
        default=None,
        description="跨方式横向对比（compare_modes=true 时）：各方式 {duration_sec, distance_m} 或 {error}",
    )
    error: Optional[str] = Field(default=None, description="该候选失败原因（成功为 null）")


class CommuteResponse(BaseModel):
    """POST /api/commute/optimal 响应 data"""

    origin: Coord
    mode: str
    results: List[CommuteResultItem] = Field(
        default_factory=list, description="成功计算的候选（按耗时升序）"
    )
    recommended: Optional[CommuteResultItem] = Field(
        default=None, description="耗时最短的候选"
    )
    errors: List[Dict[str, Any]] = Field(
        default_factory=list, description="未能计算的候选（name + error）"
    )
