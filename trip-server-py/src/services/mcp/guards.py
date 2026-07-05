"""MCP 熔断、限流和指标收集模块。

使用 pybreaker 实现熔断，使用 asyncio.Lock 实现限流，
并收集调用指标供监控使用。
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pybreaker


@dataclass
class MCPMetrics:
    """MCP 调用指标。
    
    与 Node 版 amapGuards.ts 的 AmapGuardMetrics 对齐。
    """
    calls: int = 0
    successes: int = 0
    failures: int = 0
    cache_hits: int = 0
    circuit_open_count: int = 0
    avg_duration_ms: float = 0.0


# 全局指标实例
mcp_metrics = MCPMetrics()
_total_duration_ms = 0.0
_actual_calls = 0


def reset_metrics() -> None:
    """重置所有指标（测试用）。"""
    global _total_duration_ms, _actual_calls
    mcp_metrics.calls = 0
    mcp_metrics.successes = 0
    mcp_metrics.failures = 0
    mcp_metrics.cache_hits = 0
    mcp_metrics.circuit_open_count = 0
    mcp_metrics.avg_duration_ms = 0.0
    _total_duration_ms = 0.0
    _actual_calls = 0


def get_metrics_snapshot() -> MCPMetrics:
    """获取指标快照副本。"""
    return MCPMetrics(
        calls=mcp_metrics.calls,
        successes=mcp_metrics.successes,
        failures=mcp_metrics.failures,
        cache_hits=mcp_metrics.cache_hits,
        circuit_open_count=mcp_metrics.circuit_open_count,
        avg_duration_ms=mcp_metrics.avg_duration_ms,
    )


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
    
    @property
    def opened(self) -> bool:
        """熔断器是否处于打开状态。"""
        return self._breaker.opened if hasattr(self._breaker, 'opened') else False
    
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
    
    def __init__(self, rate: float = 3.0, capacity: int = 5):
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


# Cache 实现 —— 简单 TTL 字典缓存
class MCPCache:
    """MCP 调用缓存（简单 TTL 缓存）。"""
    
    def __init__(self, ttl_seconds: int = 1800, max_size: int = 500):
        """初始化缓存。
        
        Args:
            ttl_seconds: 缓存 TTL（秒），默认 30 分钟
            max_size: 最大缓存条目数
        """
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._cache: dict[str, tuple[float, Any]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值。"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._cache[key]
            return None
        return value
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存。"""
        # 如果达到最大容量，清理过期条目
        if len(self._cache) >= self._max_size:
            self._evict_expired()
        self._cache[key] = (time.time() + self._ttl, value)
    
    def _evict_expired(self) -> None:
        """清理过期条目。"""
        now = time.time()
        expired = [k for k, (t, _) in self._cache.items() if now > t]
        for k in expired:
            del self._cache[k]
    
    def clear(self) -> None:
        """清空缓存。"""
        self._cache.clear()


# 缓存实例（按工具名分组）
mcp_cache: dict[str, MCPCache] = {}


def get_cache(tool_name: str) -> MCPCache:
    """获取或创建工具专属缓存。"""
    if tool_name not in mcp_cache:
        mcp_cache[tool_name] = MCPCache()
    return mcp_cache[tool_name]


# 工具级限流器实例
_tool_limiters: dict[str, MCPRateLimiter] = {}


def get_limiter(tool_name: str) -> MCPRateLimiter:
    """获取或创建工具专属限流器。"""
    if tool_name not in _tool_limiters:
        _tool_limiters[tool_name] = MCPRateLimiter(rate=3.0, capacity=5)
    return _tool_limiters[tool_name]


# 可缓存的工具列表（与 Node 对齐）
CACHEABLE_TOOLS = {"maps_weather", "maps_geo"}


async def call_with_guards(
    tool_name: str,
    call_fn: Callable,
    *args,
    **kwargs,
) -> Any:
    """通过熔断器 + 限流器 + 缓存 + 指标收集来调用 MCP 工具。
    
    对标 Node 版 amapGuards.ts 的 call() 方法。
    
    Args:
        tool_name: 工具名称
        call_fn: 实际调用函数
        *args, **kwargs: 传递给 call_fn 的参数
        
    Returns:
        工具调用结果
        
    Raises:
        RuntimeError: 熔断、限流或调用失败时抛出
    """
    global _total_duration_ms, _actual_calls
    
    mcp_metrics.calls += 1
    start_time = time.time()
    
    # 1. 检查缓存（仅对可缓存工具）
    if tool_name in CACHEABLE_TOOLS:
        cache_key = f"{tool_name}:{hash(tuple(args))}:{hash(frozenset(kwargs.items()))}"
        cached = get_cache(tool_name).get(cache_key)
        if cached is not None:
            mcp_metrics.cache_hits += 1
            mcp_metrics.successes += 1
            _actual_calls += 1
            duration_ms = (time.time() - start_time) * 1000
            _total_duration_ms += duration_ms
            mcp_metrics.avg_duration_ms = _total_duration_ms / _actual_calls if _actual_calls > 0 else 0.0
            return cached
    
    # 2. 限流检查
    limiter = get_limiter(tool_name)
    if not await limiter.acquire():
        mcp_metrics.failures += 1
        raise RuntimeError(f"MCP 工具 {tool_name} 被限流")
    
    # 3. 熔断器调用
    try:
        result = await mcp_circuit_breaker.call(call_fn, *args, **kwargs)
        mcp_metrics.successes += 1
        _actual_calls += 1
        
        # 写入缓存
        if tool_name in CACHEABLE_TOOLS:
            get_cache(tool_name).set(cache_key, result)
        
        # 更新平均耗时
        duration_ms = (time.time() - start_time) * 1000
        _total_duration_ms += duration_ms
        mcp_metrics.avg_duration_ms = _total_duration_ms / _actual_calls if _actual_calls > 0 else 0.0
        
        return result
        
    except Exception:
        mcp_metrics.failures += 1
        if mcp_circuit_breaker.opened:
            mcp_metrics.circuit_open_count += 1
        raise


# 全局实例
mcp_circuit_breaker = MCPCircuitBreaker()
mcp_rate_limiter = MCPRateLimiter()
