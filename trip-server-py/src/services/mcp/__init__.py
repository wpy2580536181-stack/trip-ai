"""MCP 集成模块。

提供高德地图 MCP 集成能力。
"""

from .amap_client import call_tool as amap_call_tool
from .tool_loader import load_amap_tools

__all__ = [
    "amap_call_tool",
    "load_amap_tools",
]
