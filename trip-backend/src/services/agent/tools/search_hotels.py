"""Search Hotels 工具模块。

查询目标城市的住宿信息。
迁移自 Node.js 版本的 tools/searchHotels.ts。
"""

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.services.agent.resilience import with_resilience


class SearchHotelsInput(BaseModel):
    """Search Hotels 工具输入参数。"""
    
    city: str = Field(description="目标城市名")
    budget: Optional[float] = Field(None, description="预算上限（元/晚）")
    level: Optional[str] = Field(
        None,
        description="住宿档次：economy/comfort/luxury",
    )


@tool(args_schema=SearchHotelsInput)
async def search_hotels_tool(
    city: str,
    budget: Optional[float] = None,
    level: Optional[str] = None,
) -> str:
    """查询目标城市的住宿信息。
    
    当用户询问住宿、酒店、旅馆、民宿时使用。
    
    Args:
        city: 目标城市名
        budget: 预算上限（可选）
        level: 住宿档次（可选）
        
    Returns:
        住宿信息字符串
    """
    from ...knowledge_service import search_spots
    
    try:
        # 构建搜索查询
        query_parts = []
        if level:
            query_parts.append(level)
        query_parts.append(city)
        query_parts.append("住宿酒店")
        query = " ".join(query_parts)
        
        results = await search_spots(
            query=query,
            city=city,
            category="hotel",
            limit=5,
        )
        
        if not results or results == "(未找到相关景点)":
            budget_str = f"，预算 {budget} 元/晚" if budget else ""
            return f"知识库中暂无 {city} 的住宿数据{budget_str}。请基于通用知识推荐。"
        
        return results
        
    except Exception as e:
        return f"住宿信息查询失败：{str(e)}"


# 应用韧性包装
search_hotels_tool = with_resilience(
    search_hotels_tool,
    timeout=10.0,
    retries=1,
    fallback="住宿信息暂时不可用，请基于通用旅行知识回答。",
)
