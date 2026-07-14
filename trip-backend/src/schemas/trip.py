"""Trip schemas (request/response，对齐 Node.js src/schemas/trip.ts)"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any


# ==================== 请求 Schema ====================

class RecommendRequest(BaseModel):
    """行程推荐请求"""
    model_config = ConfigDict(populate_by_name=True)

    city: str = Field(..., min_length=1, max_length=50, description="目标城市")
    budget: int = Field(..., ge=50, le=1_000_000, description="预算（元）")
    days: int = Field(..., ge=1, le=30, description="天数")
    departure_city: Optional[str] = Field(
        default=None,
        alias="departureCity",
        max_length=50,
        description="出发城市",
    )


class OptimizeRequest(BaseModel):
    """行程优化请求"""
    model_config = ConfigDict(populate_by_name=True)

    trip_id: int = Field(..., alias="tripId", gt=0, description="行程 ID")
    instruction: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="优化指令",
    )


class ChatRequest(BaseModel):
    """对话请求"""
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(..., min_length=1, description="用户消息")
    conversation_id: Optional[int] = Field(
        default=None,
        alias="conversationId",
        description="对话 ID",
    )


# ==================== 响应 Schema ====================

class SpotSchema(BaseModel):
    """景点 Schema"""
    spot: str
    duration: Optional[str] = None
    ticket: Optional[str] = None
    transportation: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = Field(default=None, alias="imageUrl")


class DailyItinerarySchema(BaseModel):
    """每日行程 Schema"""
    day: int
    date: Optional[str] = None
    morning: SpotSchema
    afternoon: SpotSchema
    evening: SpotSchema
    breakfast: Optional[SpotSchema] = None
    lunch: Optional[SpotSchema] = None
    dinner: Optional[SpotSchema] = None
    accommodation: Optional[SpotSchema] = None


class BudgetBreakdownSchema(BaseModel):
    """预算分解 Schema"""
    accommodation: float = 0
    food: float = 0
    transportation: float = 0
    tickets: float = 0
    other: float = 0


class TripDataResponse(BaseModel):
    """行程数据响应"""
    id: Optional[int] = None
    city: str
    days: int
    total_budget: Optional[float] = Field(default=None, alias="totalBudget")
    daily_itinerary: Optional[List[Any]] = Field(
        default=None, alias="dailyItinerary"
    )
    budget_breakdown: Optional[Any] = Field(
        default=None, alias="budgetBreakdown"
    )
    tips: Optional[List[str]] = None
    warnings: Optional[List[str]] = None


class TripResponse(BaseModel):
    """行程推荐/优化响应"""
    success: bool
    data: TripDataResponse


class ChatCompleteData(BaseModel):
    """chat SSE complete 事件数据"""
    conversation_id: int = Field(alias="conversationId")
    usage: Optional[dict] = None
