"""MCP 熔断和限流模块。

使用 pybreaker 实现熔断，使用 asyncio.Lock 实现限流。
"""

import asyncio
import time
from typing import Optional

import pybreaker


class MCPCircuitBreaker:
    """MCP 熔断器。"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """初始化熔断器。
        
        Args:
            failure_threshold: 失败阈值（连续失败 N 次后熔断）
            recovery_timeout: 恢复超时（秒）
        """
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=failure_threshold,
            reset_timeout=recovery_timeout,
        )
    
    async def call(self, func, *args, **kwargs):
        """通过熔断器调用函数。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._breaker.call,
            func,
            *args,
            **kwargs,
        )


class MCPRateLimiter:
    """MCP 限流器（令牌桶算法）。"""
    
    def __init__(self, rate: float = 10.0, capacity: int = 20):
        """初始化限流器。
        
        Args:
            rate: 令牌生成速率（个/秒）
            capacity: 桶容量
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """获取令牌。
        
        Returns:
            True 如果获取成功，False 如果限流
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_refill
            
            # 补充令牌
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.rate,
            )
            self._last_refill = now
            
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            
            return False
    
    async def __aenter__(self):
        """异步上下文管理器入口。"""
        if not await self.acquire():
            raise RuntimeError("MCP 请求被限流")
        return self
    
    async def __aexit__(self, *args):
        """异步上下文管理器出口。"""
        pass


# 全局实例
mcp_circuit_breaker = MCPCircuitBreaker()
mcp_rate_limiter = MCPRateLimiter()
