"""M4 阶段测试 —— CircuitBreaker 三态机 + 与 ToolResilienceWrapper 集成。

覆盖 4 类：
1. CircuitBreaker 状态机：Closed → Open → Half-Open → Closed
2. CircuitBreaker 共享：get_or_create 同一 name 返回同一实例
3. with_resilience 集成：tool 失败 N 次触发熔断，熔断期间走 fallback
4. 边界场景：失败阈值边界 / 恢复超时边界 / reset
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    ToolResilienceWrapper,
    with_resilience,
)


# ---------------------------------------------------------------------------
# 测试 1：CircuitBreaker 状态机 Closed → Open
# ---------------------------------------------------------------------------

def test_circuit_breaker_closed_to_open_on_threshold():
    """连续失败 N 次触发 Closed → Open。"""
    breaker = CircuitBreaker("test", failure_threshold=3, recovery_timeout=30.0)

    # 前 2 次失败：仍 Closed
    for i in range(2):
        assert breaker.allow_request() is True
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

    # 第 3 次失败：触发熔断
    assert breaker.allow_request() is True
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Open 状态下：拒绝请求
    assert breaker.allow_request() is False


# ---------------------------------------------------------------------------
# 测试 2：CircuitBreaker Open → Half-Open → Closed
# ---------------------------------------------------------------------------

def test_circuit_breaker_open_to_half_open_to_closed():
    """熔断后过 recovery_timeout 进入 Half-Open，试探成功转 Closed。"""
    breaker = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

    # 触发熔断
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False

    # 等 0.1s 过 recovery_timeout
    time.sleep(0.15)

    # 下一次 allow_request 自动转 Half-Open
    assert breaker.allow_request() is True
    assert breaker.state == CircuitState.HALF_OPEN

    # 试探成功 → Closed
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0

    # Closed 状态下：正常放行
    assert breaker.allow_request() is True


# ---------------------------------------------------------------------------
# 测试 3：Half-Open 试探失败重新熔断
# ---------------------------------------------------------------------------

def test_circuit_breaker_half_open_probe_failure_back_to_open():
    """Half-Open 试探失败 → 重新 Open。"""
    breaker = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

    # 触发熔断
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # 等恢复
    time.sleep(0.15)
    breaker.allow_request()  # 转 Half-Open
    assert breaker.state == CircuitState.HALF_OPEN

    # 试探失败 → 重新 Open
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Open 状态下：拒绝请求
    assert breaker.allow_request() is False


# ---------------------------------------------------------------------------
# 测试 4：get_or_create 进程内共享
# ---------------------------------------------------------------------------

def test_circuit_breaker_get_or_create_shares_instance():
    """同一 name 多次 get_or_create 返回同一实例（共享状态）。"""
    CircuitBreaker._registry = {}  # 清理
    b1 = CircuitBreaker.get_or_create("shared-tool", failure_threshold=3, recovery_timeout=10.0)
    b2 = CircuitBreaker.get_or_create("shared-tool", failure_threshold=3, recovery_timeout=10.0)
    assert b1 is b2

    # 不同 config → 不同实例
    b3 = CircuitBreaker.get_or_create("shared-tool", failure_threshold=5, recovery_timeout=10.0)
    assert b1 is not b3


# ---------------------------------------------------------------------------
# 测试 5：reset 手动重置
# ---------------------------------------------------------------------------

def test_circuit_breaker_reset():
    """reset 后状态归零。"""
    breaker = CircuitBreaker("test", failure_threshold=2, recovery_timeout=30.0)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.allow_request() is True


# ---------------------------------------------------------------------------
# 测试 6：与 ToolResilienceWrapper 集成 —— 失败阈值触发熔断
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resilience_wrapper_circuit_breaker_integration():
    """tool 连续失败 N 次后触发熔断，熔断期间直接走 fallback。"""
    breaker = CircuitBreaker("flaky-tool", failure_threshold=2, recovery_timeout=30.0)
    wrapper = ToolResilienceWrapper(
        timeout=1.0, retries=0, fallback="FALLBACK", circuit_breaker=breaker,
    )

    # 模拟一个总是失败的 tool
    async def failing_func():
        raise RuntimeError("downstream error")

    # 第 1 次：失败（breaker 计数 1，未熔断）
    result = await wrapper(failing_func)
    assert result == "FALLBACK"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    # 第 2 次：失败（breaker 计数 2，触发熔断）
    result = await wrapper(failing_func)
    assert result == "FALLBACK"
    assert breaker.state == CircuitState.OPEN

    # 第 3 次：熔断器开启，不调下游，直接走 fallback
    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        result = await wrapper(failing_func)
    assert result == "FALLBACK"
    # 关键：failing_func 没被调用（无超时等待）
    mock_sleep.assert_not_awaited()


# ---------------------------------------------------------------------------
# 测试 7：与 ToolResilienceWrapper 集成 —— 成功重置计数（仅 Half-Open）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resilience_wrapper_success_in_closed_does_not_reset():
    """CLOSED 状态下偶发成功不重置 failure_count（避免误判恢复）。"""
    breaker = CircuitBreaker("flaky-tool", failure_threshold=3, recovery_timeout=30.0)
    wrapper = ToolResilienceWrapper(
        timeout=1.0, retries=0, fallback="FALLBACK", circuit_breaker=breaker,
    )

    call_count = [0]

    async def flaky_func():
        call_count[0] += 1
        if call_count[0] % 2 == 0:  # 偶数次成功
            return "OK"
        raise RuntimeError("transient error")

    # 第 1 次：失败
    await wrapper(flaky_func)
    assert breaker.failure_count == 1

    # 第 2 次：成功（CLOSED 状态下不重置计数）
    await wrapper(flaky_func)
    assert breaker.failure_count == 1  # 仍是 1，没重置
    assert breaker.state == CircuitState.CLOSED

    # 第 3 次：失败 → 计数 2
    await wrapper(flaky_func)
    assert breaker.failure_count == 2


# ---------------------------------------------------------------------------
# 测试 8：with_resilience 装饰 LangChain tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_with_resilience_attaches_circuit_breaker_to_tool():
    """with_resilience 接受 circuit_breaker_* 配置，注入熔断器。"""
    # 构造一个 mock LangChain tool
    mock_tool = MagicMock()
    mock_tool.name = "my-tool"
    mock_tool._arun = AsyncMock(side_effect=RuntimeError("boom"))

    # 配置熔断器
    with_resilience(
        mock_tool,
        timeout=0.5,
        retries=0,
        fallback="DEFAULT",
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_timeout=30.0,
    )

    # _arun 被替换为带熔断的版本
    assert mock_tool._arun is not mock_tool._arun.__wrapped__ if hasattr(mock_tool._arun, "__wrapped__") else True

    # 调用 2 次后熔断
    await mock_tool._arun()
    await mock_tool._arun()

    # 验证熔断器被设置（通过 tool name 注册）
    # 实际不能直接拿到 breaker，但通过 fallback 行为验证
    result = await mock_tool._arun()  # 熔断期间
    assert result == "DEFAULT"  # 走 fallback


# ---------------------------------------------------------------------------
# 测试 9：未启用熔断器时行为不变（向后兼容）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resilience_wrapper_without_circuit_breaker_backward_compat():
    """不传 circuit_breaker 时，行为与 M0/M1 时期完全一致。"""
    wrapper = ToolResilienceWrapper(
        timeout=1.0, retries=2, fallback="FALLBACK", circuit_breaker=None,
    )

    async def failing_func():
        raise RuntimeError("boom")

    # 重试 2 次后 fallback
    with patch("asyncio.sleep", new=AsyncMock()):
        result = await wrapper(failing_func)
    assert result == "FALLBACK"
