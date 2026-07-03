"""高德 MCP 工具加载器模块。

动态加载 MCP tools 为 LangChain tools。
"""

import json
import logging
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


async def load_amap_tools() -> list:
    """加载高德 MCP 工具。
    
    Returns:
        LangChain StructuredTool 列表
    """
    try:
        from .amap_client import list_tools
        
        # 获取 MCP 工具列表
        mcp_tools = await list_tools()
        
        # 转换为 LangChain 工具
        langchain_tools = []
        for mcp_tool in mcp_tools:
            langchain_tool = _convert_mcp_tool_to_langchain(mcp_tool)
            langchain_tools.append(langchain_tool)
        
        logger.info(f"已加载 {len(langchain_tools)} 个高德 MCP 工具")
        return langchain_tools
        
    except Exception as e:
        logger.error(f"加载高德 MCP 工具失败: {e}")
        return []


def _convert_mcp_tool_to_langchain(mcp_tool: dict) -> StructuredTool:
    """将 MCP 工具转换为 LangChain StructuredTool。
    
    Args:
        mcp_tool: MCP 工具定义
        
    Returns:
        LangChain StructuredTool
    """
    name = mcp_tool.get("name", "unknown_tool")
    description = mcp_tool.get("description", "")
    input_schema = mcp_tool.get("inputSchema", {})
    
    # 动态创建 Pydantic 模型
    fields = {}
    properties = input_schema.get("properties", {})
    
    for prop_name, prop_def in properties.items():
        prop_type = _json_schema_type_to_python(prop_def.get("type", "string"))
        description = prop_def.get("description", "")
        fields[prop_name] = (prop_type, Field(description=description))
    
    # 创建工具函数
    async def tool_func(**kwargs: Any) -> str:
        from .amap_client import call_tool
        return await call_tool(name, kwargs)
    
    # 创建 StructuredTool
    return StructuredTool.from_function(
        name=name,
        description=description,
        func=tool_func,
        args_schema=BaseModel,
    )


def _json_schema_type_to_python(json_type: str) -> type:
    """将 JSON Schema 类型转换为 Python 类型。"""
    type_map = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return type_map.get(json_type, str)
