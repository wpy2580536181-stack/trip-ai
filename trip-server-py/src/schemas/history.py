"""History schemas (request/response)"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any


class TripResponse(BaseModel):
    """行程响应"""
    model_config = ConfigDict(
        serialize_by_alias=True,
        from_attributes=True
    )
    
    id: int
    user_id: int = Field(alias="userId")
    from_city: Optional[str] = Field(default=None, alias="fromCity")
    city: str
    days: int
    budget: int
    content: Dict[str, Any]
    status: str = "completed"
    parent_trip_id: Optional[int] = Field(default=None, alias="parentTripId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")


class TripListResponse(BaseModel):
    """行程历史列表响应"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    items: List[TripResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
