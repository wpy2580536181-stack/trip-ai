"""Tool Resilience 模块。

为工具调用添加超时、重试和降级能力。
迁移自 Node.js 版本的 resilience.ts。
"""

import asyncio
import functools
from typing import Any, Callable, Awaitable, Optional

import httpx


class ToolResilienceWrapper:
    """工具韧性包装器。
    
    为异步工具函数添加：
    - 超时保护
    - 自动重试
    - 降级返回值
    """
    
    def __init__(
        self,
        timeout: float = 10.0,
        retries: int = 2,
        fallback: Any = None,
        on_failure: Optional[Callable[[Exception], Awaitable[None]]] = None,
    ):
        """初始化韧性包装器。
        
        Args:
            timeout: 超时时间（秒）
            retries: 重试次数
            fallback: 降级返回值（超时或重试失败时返回）
            on_failure: 失败时的回调函数（可选）
        """
        self.timeout = timeout
        self.retries = retries
        self.fallback = fallback
        self.on_failure = on_failure

    @staticmethod
    def _extract_retry_after(exc: Optional[Exception]) -> Optional[float]:
        """从 httpx 的 429 异常中提取 Retry-After 等待秒数（无则返回 None）。"""
        if isinstance(exc, httpx.HTTPStatusError):
            resp = getattr(exc, "response", None)
            if resp is not None and getattr(resp, "status_code", None) == 429:
                raw = resp.headers.get("Retry-After") if resp.headers else None
                if raw:
                    try:
                        secs = float(str(raw).strip())
                        if secs >= 0:
                            return secs
                    except (ValueError, TypeError):
                        pass
        return None

    def _compute_backoff(self, exc: Optional[Exception], attempt: int) -> float:
        """计算退避等待秒数。

        - 上游 429：优先使用 Retry-After（封顶 30s）
        - 其余：指数退避 2**attempt（封顶 10s）
        """
        retry_after = self._extract_retry_after(exc) if exc is not None else None
        if retry_after is not None:
            return min(retry_after, 30.0)
        return min(2 ** attempt, 10)

    async def __call__(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """执行被包装的函数（带超时、重试、降级）。
        
        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果，或降级值
        """
        last_error = None
        
        for attempt in range(self.retries + 1):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError as e:
                last_error = e
                if self.on_failure:
                    try:
                        await self.on_failure(e)
                    except Exception:
                        pass  # 忽略回调失败
            except Exception as e:
                last_error = e
                if self.on_failure:
                    try:
                        await self.on_failure(e)
                    except Exception:
                        pass
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < self.retries:
                wait_time = self._compute_backoff(last_error, attempt)
                await asyncio.sleep(wait_time)
        
        # 所有重试都失败，返回降级值
        return self.fallback


def with_resilience(tool: Any, **resilience_config: Any) -> Any:
    """为 LangChain 工具添加韧性包装。
    
    Args:
        tool: LangChain 工具实例
        **resilience_config: 韧性配置（timeout, retries, fallback）
        
    Returns:
        包装后的工具
    """
    timeout = resilience_config.get("timeout", 10.0)
    retries = resilience_config.get("retries", 2)
    fallback = resilience_config.get("fallback", None)
    
    wrapper = ToolResilienceWrapper(
        timeout=timeout,
        retries=retries,
        fallback=fallback,
    )
    
    # 保存原始工具的 _arun 方法
    original_arun = tool._arun if hasattr(tool, "_arun") else None
    
    if original_arun:
        # 创建新的 _arun 方法
        async def resilient_arun(*args: Any, **kwargs: Any) -> Any:
            return await wrapper(original_arun, *args, **kwargs)
        
        tool._arun = resilient_arun
    
    return tool
