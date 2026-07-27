"""Knowledge schemas (request/response)"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any


class SpotResponse(BaseModel):
    """景点响应"""
    model_config = ConfigDict(
        serialize_by_alias=True,
        from_attributes=True
    )
    
    id: int
    name: str
    city: str
    category: str
    description: str
    tags: List[str]
    avg_cost: Optional[float] = Field(default=None, alias="avgCost")
    duration: Optional[str] = None
    open_time: Optional[str] = Field(default=None, alias="openTime")
    rating: Optional[float] = None
    has_embedding: Optional[bool] = Field(default=None, alias="hasEmbedding")
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")


class SpotCreate(BaseModel):
    """创建景点请求（admin）"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    name: str = Field(..., description="景点名称")
    city: str = Field(..., description="城市")
    category: str = Field(..., description="分类")
    description: str = Field(..., description="描述")
    tags: List[str] = Field(default=[], description="标签")
    avg_cost: Optional[float] = Field(None, alias="avgCost", description="平均花费")
    duration: Optional[str] = Field(None, description="推荐游览时长")
    open_time: Optional[str] = Field(None, alias="openTime", description="开放时间")
    rating: Optional[float] = Field(None, description="评分")


class SpotUpdate(BaseModel):
    """更新景点请求（admin）"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    name: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    avg_cost: Optional[float] = Field(None, alias="avgCost")
    duration: Optional[str] = None
    open_time: Optional[str] = Field(None, alias="openTime")
    rating: Optional[float] = None


class SpotListResponse(BaseModel):
    """景点列表响应"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    items: List[SpotResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")


class SpotDocCreate(BaseModel):
    """文本层文档块创建（ETL 写入）"""
    model_config = ConfigDict(serialize_by_alias=True)

    spot_id: int = Field(..., description="关联景点 ID")
    source_type: str = Field(..., description="来源类型: wiki/wikidata/official_gov/gaode_detail/...")
    source_name: Optional[str] = Field(None, description="来源名称")
    source_url: Optional[str] = Field(None, description="原文链接")
    title: Optional[str] = Field(None, description="文本块标题")
    content: str = Field(..., description="分块文本内容")
    chunk_index: int = Field(0, description="分块序号")
    published_at: Optional[str] = Field(None, description="原文发布时间(ISO)")
    # 可信度元信息（可选，缺省由 compute_credibility 计算）
    authority_score: Optional[float] = None
    freshness_score: Optional[float] = None
    agreement_score: Optional[float] = None
    citation_count: Optional[int] = None
    evidence_density: Optional[float] = None
    credibility_score: Optional[float] = None


class SpotDocResponse(BaseModel):
    """文本层文档块响应"""
    model_config = ConfigDict(serialize_by_alias=True, from_attributes=True)

    id: int
    spot_id: int
    source_type: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    title: Optional[str] = None
    content: str
    chunk_index: int
    authority_score: Optional[float] = None
    freshness_score: Optional[float] = None
    agreement_score: Optional[float] = None
    citation_count: Optional[int] = None
    evidence_density: Optional[float] = None
    credibility_score: Optional[float] = None
    published_at: Optional[str] = None
    retrieved_at: Optional[str] = None
