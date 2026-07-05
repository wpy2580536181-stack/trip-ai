"""Agent 工具模块。

导出所有工具函数。
在导出时应用 ToolCache 包装（套在 with_resilience 外层）。
"""

from .retrieve_knowledge import retrieve_knowledge_tool
from .calculate_distance import calculate_distance_tool
from .search_hotels import search_hotels_tool

# 应用 ToolCache 包装（套在 with_resilience 外层）
try:
    from src.services.agent.tool_cache import get_tool_cache, with_tool_cache

    _tc = get_tool_cache()
    if _tc is not None:
        retrieve_knowledge_tool = with_tool_cache(retrieve_knowledge_tool, _tc, "retrieve_knowledge")
        calculate_distance_tool = with_tool_cache(calculate_distance_tool, _tc, "calculate_distance")
        search_hotels_tool = with_tool_cache(search_hotels_tool, _tc, "search_hotels")
except Exception:
    pass  # ToolCache 不可用时静默降级

__all__ = [
    "retrieve_knowledge_tool",
    "calculate_distance_tool",
    "search_hotels_tool",
]
