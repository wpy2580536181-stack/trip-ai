"""高德 MCP 客户端模块。

使用 asyncio.subprocess 管理高德 MCP server 进程，
实现 stdio JSON-RPC 通信协议。
"""

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# MCP server 进程
_mcp_process: Optional[asyncio.subprocess.Process] = None
_mcp_lock = asyncio.Lock()

# JSON-RPC 请求 ID 计数器
_request_id = 0
_request_id_lock = asyncio.Lock()


async def _ensure_mcp_process() -> asyncio.subprocess.Process:
    """确保 MCP server 进程已启动。"""
    global _mcp_process
    
    async with _mcp_lock:
        if _mcp_process and _mcp_process.returncode is None:
            return _mcp_process
        
        # 启动新进程
        from ..config.settings import settings
        
        cmd = [
            "node",
            settings.AMAP_MCP_SERVER_PATH,
        ]
        
        _mcp_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # 等待进程就绪
        await asyncio.sleep(1)
        
        if _mcp_process.returncode is not None:
            raise RuntimeError("高德 MCP server 进程启动失败")
        
        logger.info("高德 MCP server 进程已启动")
        return _mcp_process


async def _send_request(method: str, params: dict) -> Any:
    """发送 JSON-RPC 请求。
    
    Args:
        method: RPC 方法名
        params: 方法参数
        
    Returns:
        RPC 响应结果
    """
    global _request_id
    
    async with _request_id_lock:
        _request_id += 1
        current_id = _request_id
    
    request = {
        "jsonrpc": "2.0",
        "id": current_id,
        "method": method,
        "params": params,
    }
    
    process = await _ensure_mcp_process()
    
    # 发送请求
    request_str = json.dumps(request, ensure_ascii=False) + "\n"
    process.stdin.write(request_str.encode())
    await process.stdin.drain()
    
    # 读取响应
    response_line = await asyncio.wait_for(
        process.stdout.readline(),
        timeout=30.0,
    )
    
    if not response_line:
        raise RuntimeError("MCP server 未返回响应")
    
    response = json.loads(response_line.decode())
    
    if "error" in response:
        error = response["error"]
        raise RuntimeError(f"MCP 错误: {error.get('message', '未知错误')}")
    
    return response.get("result")


async def call_tool(tool_name: str, arguments: dict) -> str:
    """调用高德 MCP 工具。
    
    Args:
        tool_name: 工具名称（如 "maps_weather"）
        arguments: 工具参数
        
    Returns:
        工具执行结果字符串
    """
    try:
        result = await _send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )
        
        # 提取结果文本
        content = result.get("content", [])
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts)
        
        return str(result)
        
    except Exception as e:
        logger.error(f"调用 MCP 工具失败: {tool_name}, {e}")
        raise


async def list_tools() -> list[dict]:
    """列出可用的 MCP 工具。"""
    try:
        result = await _send_request("tools/list", {})
        return result.get("tools", [])
    except Exception as e:
        logger.error(f"列出 MCP 工具失败: {e}")
        return []


async def close_mcp_process() -> None:
    """关闭 MCP server 进程。"""
    global _mcp_process
    
    async with _mcp_lock:
        if _mcp_process and _mcp_process.returncode is None:
            _mcp_process.terminate()
            await _mcp_process.wait()
            logger.info("高德 MCP server 进程已关闭")
            _mcp_process = None
