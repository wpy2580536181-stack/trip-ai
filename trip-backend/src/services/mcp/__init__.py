"""MCP 集成模块。

提供高德地图 MCP 集成能力。
"""

from .amap_client import call_tool as amap_call_tool
from .amap_process import is_amap_mcp_alive
from .tool_loader import load_amap_tools
from .guards import mcp_metrics, get_metrics_snapshot, reset_metrics

__all__ = [
    "amap_call_tool",
    "is_amap_mcp_alive",
    "load_amap_tools",
    "mcp_metrics",
    "get_metrics_snapshot",
    "reset_metrics",
]
