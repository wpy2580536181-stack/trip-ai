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
    """确保 MCP server 进程已启动。

    通过 npx 运行 @amap/amap-maps-mcp-server，自动下载无需手动安装。
    环境变量 AMAP_KEY 由 settings.amap_maps_api_key 注入。
    """
    global _mcp_process

    async with _mcp_lock:
        if _mcp_process and _mcp_process.returncode is None:
            return _mcp_process

        from src.config.settings import settings

        if not settings.amap_maps_api_key:
            raise RuntimeError("AMAP_MAPS_API_KEY not configured, cannot start Amap MCP server")

        # 使用 npx 自动解析 @amap/amap-maps-mcp-server，无需预安装
        # amap_mcp_server_path 配置为 "npx"（或 npx 的绝对路径，如 /usr/local/bin/npx）
        cmd = [settings.amap_mcp_server_path or "npx", "-y", "@amap/amap-maps-mcp-server"]

        # 注入环境变量：高德 MCP server 需要 AMAP_MAPS_API_KEY
        # 保留 AMAP_KEY 作为 fallback（兼容旧版 npm 包）
        env = {
            **__import__("os").environ,
            "AMAP_MAPS_API_KEY": settings.amap_maps_api_key,
            "AMAP_KEY": settings.amap_maps_api_key,
        }

        logger.info("Starting Amap MCP server", extra={"cmd": " ".join(cmd)})
        _mcp_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # 轮询探测 server 就绪：发送 tools/list 握手请求并等待带超时的响应。
        # 固定 sleep(2) 无法区分“已就绪”与“npx 仍在下载/启动”（此时 returncode 为 None），
        # 首次调用可能因 server 未就绪而干等 30s 超时。
        ready = False
        for _ in range(10):
            if _mcp_process.returncode is not None:
                stderr = (await _mcp_process.stderr.read()).decode() if _mcp_process.stderr else ""
                raise RuntimeError(f"高德 MCP server 启动失败 (exit {_mcp_process.returncode}): {stderr[:200]}")

            try:
                # 直接向子进程 stdin/stdout 握手（不走 _send_request，避免递归调用 _ensure_mcp_process）
                probe = json.dumps({"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}}).encode() + b"\n"
                _mcp_process.stdin.write(probe)
                await _mcp_process.stdin.drain()
                line = await asyncio.wait_for(_mcp_process.stdout.readline(), timeout=1.0)
                if line:
                    try:
                        resp = json.loads(line.decode())
                    except json.JSONDecodeError:
                        continue
                    # 校验响应对应本次握手请求（id=0），避免误读其他输出
                    if resp.get("id") == 0 and "result" in resp:
                        ready = True
                        break
            except (asyncio.TimeoutError, OSError, ValueError):
                pass
            await asyncio.sleep(1)

        if not ready:
            raise RuntimeError("高德 MCP server 启动超时（10s），未能完成 tools/list 握手")

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
    
    通过 guards 模块（熔断器 + 限流器 + 缓存）保护调用，
    并自动收集指标供 /api/admin/mcp-stats 端点使用。
    
    Args:
        tool_name: 工具名称（如 "maps_weather"）
        arguments: 工具参数
        
    Returns:
        工具执行结果字符串
    """
    from src.services.mcp.guards import call_with_guards

    async def _do_call() -> str:
        """实际的工具调用逻辑（不包含 guards 层）。"""
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

    try:
        return await call_with_guards(tool_name, _do_call)
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
