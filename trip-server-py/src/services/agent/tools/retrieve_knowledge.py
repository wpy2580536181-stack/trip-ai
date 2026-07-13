"""Retrieve Knowledge 工具模块。

从知识库检索景点信息。
迁移自 Node.js 版本的 tools/retrieveKnowledge.ts。
"""

import json
import logging
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.services.agent.resilience import with_resilience

logger = logging.getLogger(__name__)


class RetrieveKnowledgeInput(BaseModel):
    """Retrieve Knowledge 工具输入参数。"""
    
    query: str = Field(description="搜索关键词，描述你想了解的景点主题")
    city: str = Field(description="目标城市名")
    category: Optional[str] = Field(
        None,
        description="景点类型：景点/美食/住宿/交通",
    )


@tool(args_schema=RetrieveKnowledgeInput)
async def retrieve_knowledge_tool(query: str, city: str, category: Optional[str] = None) -> str:
    """从旅行知识库检索景点、美食、住宿、交通等真实信息。
    
    当用户询问某个城市具体的景点推荐、美食、交通、住宿时，必须调用此工具获取真实数据。
    
    Args:
        query: 搜索关键词
        city: 目标城市名
        category: 景点类型（可选）
        
    Returns:
        检索结果字符串
    """
    from ...knowledge_service import search_spots
    from ...poi_cache import get_poi_cache
    
    # ---- POI 缓存检查 ----
    search_category = category or "attraction"
    poi_cache = get_poi_cache()
    
    if search_category in ("attraction", "food"):
        cached = await poi_cache.get(city, search_category, query)
        if cached is not None:
            return cached
    
    try:
        results = await search_spots(
            query=query,
            city=city,
            category=category,
            limit=5,
        )
        
        if not results:
            return f"知识库中没有找到 {city} 的相关信息。"
        
        # ---- POI 缓存写入 ----
        if search_category in ("attraction", "food"):
            await poi_cache.set(city, search_category, query, results)
        
        return results
        
    except Exception as e:
        return f"知识库检索失败：{str(e)}"


# 应用韧性包装（超时 + 重试 + 降级）
retrieve_knowledge_tool = with_resilience(
    retrieve_knowledge_tool,
    timeout=15.0,  # 15 秒超时
    retries=1,
    fallback="知识库暂时不可用，请基于通用旅行知识回答。",
)
