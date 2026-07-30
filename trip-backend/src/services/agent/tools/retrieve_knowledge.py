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

# LLM 可能传中文分类名，数据库用英文
_CATEGORY_MAP = {
    "景点": "attraction",
    "美食": "food",
    "住宿": "hotel",
    "交通": "transportation",
}


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
    from ...knowledge_service import search_spots, KnowledgeService
    from ...poi_cache import get_poi_cache
    
    # ---- 分类名归一化 ----
    # 如果 LLM 未传分类，从 query 关键词推断
    if not category:
        _food_kw = {"美食", "好吃的", "餐厅", "吃", "饭", "早饭", "午饭", "晚饭", "早餐", "午餐", "晚餐"}
        _spot_kw = {"景点", "好玩", "逛", "游览", "参观", "玩"}
        if any(kw in query for kw in _food_kw):
            category = "美食"
        elif any(kw in query for kw in _spot_kw):
            category = "景点"
    db_category = _CATEGORY_MAP.get(category, category) if category else None
    search_category = db_category or "attraction"
    poi_cache = get_poi_cache()
    
    if search_category in ("attraction", "food"):
        cached = await poi_cache.get(city, search_category, query)
        if cached is not None:
            return cached
    
    try:
        results = await search_spots(
            query=query,
            city=city,
            category=search_category,  # 始终传有效分类，避免无分类过滤返回酒店等高评分干扰项
            limit=5,
        )

        if not results:
            return f"知识库中没有找到 {city} 的相关信息。"

        # 富化：把文本层真实证据（来源片段 / 可信度 / 原文链接）拼进上下文，
        # 让 LLM 拿到模型参数外的真实信息，并能引用出处。
        formatted = await KnowledgeService.format_search_results(results, include_details=True)

        # ---- POI 缓存写入 ----
        if search_category in ("attraction", "food"):
            await poi_cache.set(city, search_category, query, formatted)

        return formatted

    except Exception as e:
        return f"知识库检索失败：{str(e)}"


# 应用韧性包装（超时 + 重试 + 熔断 + 降级）
retrieve_knowledge_tool = with_resilience(
    retrieve_knowledge_tool,
    timeout=8.0,  # 8 秒超时
    retries=0,  # 不重试，快速返回 fallback 让 LLM 基于通用知识回答
    fallback="知识库暂时不可用，请基于通用旅行知识回答。",
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=30.0,
)
