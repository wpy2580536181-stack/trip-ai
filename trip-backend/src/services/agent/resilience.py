"""Tool Resilience 模块。

为工具调用添加超时、重试、熔断、降级能力。
迁移自 Node.js 版本的 resilience.ts。

M4 改造：新增 CircuitBreaker 三态机（Closed/Open/Half-Open），与
ToolResilienceWrapper 组合使用（circuit_breaker=True 启用）。

设计要点：
- 熔断与降级解耦：熔断是状态机（什么时候调用下游），降级是默认值（下游失败返回什么）
- 状态转换写日志（trip_log.info），便于排错 + 面试讲故事
- CircuitBreaker 是独立类，**按 tool name 共享**（同一 tool 多次调用共享同一熔断器）
"""
import asyncio
import enum
import functools
import time
from typing import Any, Callable, Awaitable, Optional

import httpx

from langchain_core.runnables import RunnableConfig

from src.utils.logger import trip_log


# ---------------------------------------------------------------------------
# Circuit Breaker 三态机（M4 新增）
# ---------------------------------------------------------------------------


class CircuitState(enum.Enum):
    """熔断器状态。"""
    CLOSED = "closed"        # 正常：所有请求通过
    OPEN = "open"            # 熔断：所有请求直接走 fallback，不调下游
    HALF_OPEN = "half_open"  # 试探：放行 1 个请求试探恢复


class CircuitBreakerOpenError(Exception):
    """熔断器开启时抛错（让 wrapper 走 fallback）。"""
    def __init__(self, name: str, recovery_in_s: float):
        super().__init__(f"circuit_breaker_open: {name}, recovery_in={recovery_in_s:.1f}s")
        self.name = name
        self.recovery_in_s = recovery_in_s


class CircuitBreaker:
    """熔断器（按 name 共享，进程内单例）。

    三态转换：
    - CLOSED → OPEN：连续失败次数达到 `failure_threshold`（默认 5）
    - OPEN → HALF_OPEN：经过 `recovery_timeout`（默认 30s）
    - HALF_OPEN → CLOSED：试探请求成功
    - HALF_OPEN → OPEN：试探请求失败

    用法：
        breaker = CircuitBreaker("amap", failure_threshold=5, recovery_timeout=30)
        wrapper = ToolResilienceWrapper(..., circuit_breaker=breaker)
        result = await wrapper(tool._arun, ...)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        """初始化熔断器。

        Args:
            name: 熔断器名称（一般用 tool 名，便于日志/监控识别）
            failure_threshold: 触发熔断的连续失败次数（默认 5）
            recovery_timeout: 熔断后多久进入 Half-Open 试探（秒，默认 30）
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_at: Optional[float] = None
        # 进程内共享同一 name 的熔断器（避免同一 tool 多次创建 breaker）
        self._registry: dict[str, "CircuitBreaker"] = {}

    @classmethod
    def get_or_create(
        cls,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> "CircuitBreaker":
        """按 name 进程内共享（同一 tool 多次调用共享同一熔断器）。"""
        if not hasattr(cls, "_registry"):
            cls._registry = {}
        registry_key = f"{name}:{failure_threshold}:{recovery_timeout}"
        if registry_key not in cls._registry:
            cls._registry[registry_key] = cls(
                name, failure_threshold, recovery_timeout,
            )
        return cls._registry[registry_key]

    @property
    def state(self) -> CircuitState:
        """当前状态（外部只读，状态变化由内部方法驱动）。"""
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def allow_request(self) -> bool:
        """检查是否允许请求通过。

        Returns:
            True: CLOSED 状态 或 HALF_OPEN 状态（试探）
            False: OPEN 状态（直接拒绝，让 wrapper 走 fallback）
        """
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            # 检查是否到 recovery_timeout
            if self._last_failure_at is not None and (
                time.time() - self._last_failure_at >= self.recovery_timeout
            ):
                self._transition(CircuitState.HALF_OPEN, reason="recovery_timeout_reached")
                return True
            return False
        # HALF_OPEN：放行 1 个试探请求（多次调用会一起放行，靠 record_success/failure 收敛）
        return True

    def record_success(self) -> None:
        """记录成功调用。"""
        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.CLOSED, reason="probe_success")
        # CLOSED 状态下成功是常态，不重置 failure_count（用连续失败判定熔断）
        # 成功一次不重置是为了避免偶发成功"打断"连续失败累积

    def record_failure(self) -> None:
        """记录失败调用。"""
        self._failure_count += 1
        self._last_failure_at = time.time()
        if self._state == CircuitState.HALF_OPEN:
            # 试探失败 → 重新熔断
            self._transition(CircuitState.OPEN, reason="probe_failed")
            return
        if self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._transition(CircuitState.OPEN, reason="failure_threshold_reached")

    def _transition(self, new_state: CircuitState, reason: str = "") -> None:
        """状态切换（内部用）。"""
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
        trip_log.info(
            "circuit_breaker_state_transition",
            name=self.name,
            from_state=old_state.value,
            to_state=new_state.value,
            reason=reason,
            failure_count=self._failure_count,
        )

    def reset(self) -> None:
        """手动重置（测试/管理用）。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_at = None


class ToolResilienceWrapper:
    """工具韧性包装器。

    为异步工具函数添加：
    - 超时保护
    - 自动重试
    - **熔断器**（M4 新增，circuit_breaker=CircuitBreaker(...) 启用）
    - 降级返回值

    设计：熔断与降级解耦——
    - 熔断（circuit_breaker）：决定是否调下游（避免拖垮）
    - 降级（fallback）：下游失败时返回什么默认值
    """

    def __init__(
        self,
        timeout: float = 10.0,
        retries: int = 2,
        fallback: Any = None,
        on_failure: Optional[Callable[[Exception], Awaitable[None]]] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        """初始化韧性包装器。

        Args:
            timeout: 超时时间（秒）
            retries: 重试次数
            fallback: 降级返回值（超时或重试失败时返回）
            on_failure: 失败时的回调函数（可选）
            circuit_breaker: 熔断器实例（M4 新增，None 禁用熔断）
        """
        self.timeout = timeout
        self.retries = retries
        self.fallback = fallback
        self.on_failure = on_failure
        self.circuit_breaker = circuit_breaker

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
        """执行被包装的函数（带超时、重试、熔断、降级）。

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果，或降级值
        """
        # 熔断器检查（M4 新增）
        if self.circuit_breaker is not None and not self.circuit_breaker.allow_request():
            trip_log.warning(
                "circuit_breaker_open_reject",
                name=self.circuit_breaker.name,
                recovery_in_s=self.circuit_breaker.recovery_timeout,
            )
            return self.fallback

        last_error = None

        for attempt in range(self.retries + 1):
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.timeout,
                )
                # 成功 → 通知熔断器（M4 新增）
                if self.circuit_breaker is not None:
                    self.circuit_breaker.record_success()
                return result
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

            # 失败 → 通知熔断器（M4 新增）
            if self.circuit_breaker is not None:
                self.circuit_breaker.record_failure()

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
        **resilience_config: 韧性配置
            - timeout: 超时时间（秒，默认 10）
            - retries: 重试次数（默认 2）
            - fallback: 降级返回值
            - on_failure: 失败回调
            - circuit_breaker_failure_threshold: 触发熔断的连续失败次数（M4 新增）
            - circuit_breaker_recovery_timeout: 熔断后多久进入 Half-Open（秒，M4 新增）

    Returns:
        包装后的工具
    """
    timeout = resilience_config.get("timeout", 10.0)
    retries = resilience_config.get("retries", 2)
    fallback = resilience_config.get("fallback", None)
    on_failure = resilience_config.get("on_failure", None)

    # M4 新增：熔断器（按 tool 名进程内共享）
    circuit_breaker: Optional[CircuitBreaker] = None
    if "circuit_breaker_failure_threshold" in resilience_config or \
       "circuit_breaker_recovery_timeout" in resilience_config:
        tool_name = getattr(tool, "name", tool.__class__.__name__)
        circuit_breaker = CircuitBreaker.get_or_create(
            name=tool_name,
            failure_threshold=resilience_config.get("circuit_breaker_failure_threshold", 5),
            recovery_timeout=resilience_config.get("circuit_breaker_recovery_timeout", 30.0),
        )

    wrapper = ToolResilienceWrapper(
        timeout=timeout,
        retries=retries,
        fallback=fallback,
        on_failure=on_failure,
        circuit_breaker=circuit_breaker,
    )

    # 保存原始工具的 _arun 方法
    original_arun = tool._arun if hasattr(tool, "_arun") else None

    if original_arun:
        # 创建新的 _arun 方法，保持与原始 _arun 一致的签名
        # 原始 _arun 签名：(self, *args, config: RunnableConfig, run_manager=None, **kwargs)
        # 必须显式声明 config: RunnableConfig 参数，否则 arun() 无法通过
        # _get_runnable_config_param 检测到 config 参数，不会传递 config 到 kwargs
        async def resilient_arun(
            *args: Any,
            config: RunnableConfig,
            run_manager: Optional[Any] = None,
            **kwargs: Any,
        ) -> Any:
            return await wrapper(original_arun, *args, config=config, run_manager=run_manager, **kwargs)

        tool._arun = resilient_arun

    return tool
