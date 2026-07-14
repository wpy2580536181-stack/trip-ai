"""高德 MCP 进程管理模块。

管理高德 MCP server 子进程的生命周期。
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全局进程引用
_mcp_process: Optional[asyncio.subprocess.Process] = None
_mcp_lock = asyncio.Lock()


async def start_amap_mcp_server() -> asyncio.subprocess.Process:
    """启动高德 MCP server 子进程。
    
    Returns:
        子进程对象
    """
    global _mcp_process
    
    async with _mcp_lock:
        if _mcp_process and _mcp_process.returncode is None:
            return _mcp_process
        
        # 从配置中读取 server 路径
        from src.config.settings import settings
        
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


async def stop_amap_mcp_server() -> None:
    """停止高德 MCP server 子进程。"""
    global _mcp_process
    
    async with _mcp_lock:
        if _mcp_process and _mcp_process.returncode is None:
            _mcp_process.terminate()
            await _mcp_process.wait()
            logger.info("高德 MCP server 进程已停止")
            _mcp_process = None


async def get_amap_mcp_process() -> Optional[asyncio.subprocess.Process]:
    """获取高德 MCP server 进程（如果已启动）。"""
    async with _mcp_lock:
        return _mcp_process


async def is_amap_mcp_alive() -> bool:
    """检查高德 MCP server 进程是否存活。
    
    与 Node 版 amapMcpProcess.isAlive() 对齐。
    
    Returns:
        True 如果进程存在且仍在运行
    """
    async with _mcp_lock:
        return (
            _mcp_process is not None
            and _mcp_process.returncode is None
        )
