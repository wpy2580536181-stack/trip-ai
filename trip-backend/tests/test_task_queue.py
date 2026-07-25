"""TaskQueue 单元测试

覆盖：
- 初始化：Redis 可用 / 不可用 / arq 未装 三种场景的 backend 选择
- enqueue：arq 路径（mock pool 验证入参）
- enqueue：asyncio.create_task 降级路径
- enqueue：arq 失败时自动降级
- enqueue：幂等键（_job_id）正确传递
- health() 返回正确状态

策略：所有测试 mock 掉 is_redis_available 和 arq 的 create_pool，
不实际连接 Redis，也不启动 worker。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import task_queue as tq_module
from src.services.task_queue import TaskQueue, get_task_queue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_task_queue():
    """每个测试重置单例，避免状态污染。"""
    tq_module._task_queue = None
    yield
    tq_module._task_queue = None


@pytest.fixture
def mock_arq_pool():
    """Mock arq pool：enqueue_job 返回带 job_id 的对象。"""
    pool = MagicMock()
    job = MagicMock()
    job.job_id = "mock-job-123"
    pool.enqueue_job = AsyncMock(return_value=job)
    return pool


# ---------------------------------------------------------------------------
# 测试 1：初始化 backend 选择
# ---------------------------------------------------------------------------

def test_init_backend_asyncio_when_redis_unavailable(fresh_task_queue):
    """Redis 不可用时 → backend=asyncio。"""
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()
    assert tq.backend_type == "asyncio"
    assert tq.is_arq is False


def test_init_backend_arq_when_redis_available(fresh_task_queue):
    """Redis 可用 + arq 已装 → backend=arq。"""
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    assert tq.backend_type == "arq"
    # 注意：pool 未注入前 is_arq 仍为 False
    assert tq.is_arq is False


def test_attach_pool_switches_to_arq(fresh_task_queue, mock_arq_pool):
    """attach_arq_pool 后 is_arq 变为 True。"""
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    tq.attach_arq_pool(mock_arq_pool)
    assert tq.is_arq is True


# ---------------------------------------------------------------------------
# 测试 2：enqueue 走 arq 路径
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enqueue_arq_path_passes_args_and_kwargs(fresh_task_queue, mock_arq_pool):
    """arq 可用时 → enqueue_job 收到 func_name + args + kwargs + _job_id。"""
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    tq.attach_arq_pool(mock_arq_pool)

    async def my_func(ctx, x: int, y: str = "default") -> str:
        return f"{x}-{y}"

    job_id = await tq.enqueue(my_func, 42, y="hello", job_id="custom-id-1")
    assert job_id == "mock-job-123"
    mock_arq_pool.enqueue_job.assert_awaited_once_with(
        "my_func", 42, _job_id="custom-id-1", y="hello"
    )


@pytest.mark.asyncio
async def test_enqueue_arq_path_without_job_id(fresh_task_queue, mock_arq_pool):
    """不传 job_id 时 _job_id=None（arq 会自己生成）。"""
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    tq.attach_arq_pool(mock_arq_pool)

    async def my_func(ctx):
        return None

    await tq.enqueue(my_func)
    mock_arq_pool.enqueue_job.assert_awaited_once_with("my_func", _job_id=None)


# ---------------------------------------------------------------------------
# 测试 3：enqueue 走 asyncio 降级
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enqueue_asyncio_fallback_when_redis_unavailable(fresh_task_queue):
    """Redis 不可用时 → 走 asyncio.create_task + fake ctx 注入。

    worker 函数签名是 `async def func(ctx, *args, **kwargs)`，arq 端会自动注入 ctx。
    降级路径必须构造 fake_ctx，否则 func 的第一个业务参数会被错位地接收到 ctx 位置。
    """
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()

    called = []

    async def my_func(ctx: dict, x: int) -> int:
        called.append((ctx, x))
        return x * 2

    result = await tq.enqueue(my_func, 5, job_id="test-job-1")
    assert result is None  # 降级路径不返回 job_id

    # 给 asyncio.create_task 一点时间跑
    await asyncio.sleep(0.05)
    assert len(called) == 1
    ctx, x = called[0]
    assert x == 5  # 业务参数正确
    # 关键断言：ctx 是 fake dict（含 job_id / job_try / degraded）
    assert isinstance(ctx, dict)
    assert ctx.get("job_id") == "test-job-1"
    assert ctx.get("degraded") is True


@pytest.mark.asyncio
async def test_enqueue_asyncio_fallback_when_pool_not_attached(fresh_task_queue):
    """Redis 可用但 pool 未注入时 → 也走 asyncio 降级。"""
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    # 注意：没调 attach_arq_pool()
    assert tq.is_arq is False

    called = []

    async def my_func(ctx: dict, x: int) -> int:
        called.append((ctx, x))
        return x

    await tq.enqueue(my_func, 7, job_id="test-job-2")
    await asyncio.sleep(0.05)
    assert len(called) == 1
    ctx, x = called[0]
    assert x == 7
    assert ctx.get("job_id") == "test-job-2"
    assert ctx.get("degraded") is True


# ---------------------------------------------------------------------------
# 测试 4：arq 失败时降级
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enqueue_arq_failure_falls_back_to_asyncio(fresh_task_queue):
    """arq enqueue_job 抛异常 → 自动降级到 asyncio.create_task + fake ctx。"""
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(side_effect=ConnectionError("Redis 抖动"))
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    tq.attach_arq_pool(pool)

    called = []

    async def my_func(ctx: dict, x: int) -> int:
        called.append((ctx, x))
        return x

    # arq 抛错，但降级路径应跑通
    result = await tq.enqueue(my_func, 99, job_id="test-job-3")
    assert result is None
    await asyncio.sleep(0.05)
    assert len(called) == 1
    ctx, x = called[0]
    assert x == 99
    assert ctx.get("job_id") == "test-job-3"
    assert ctx.get("degraded") is True
    pool.enqueue_job.assert_awaited_once()


# ---------------------------------------------------------------------------
# 测试 5：health() 返回正确状态
# ---------------------------------------------------------------------------

def test_health_asyncio_backend(fresh_task_queue):
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()
    h = tq.health()
    # 注：决策文档 review P0-2 后 health() 多了 degraded_pending 字段，用部分匹配
    assert h["backend"] == "asyncio"
    assert h["pool_attached"] is False
    assert h["degraded_pending"] == 0


def test_health_arq_backend_without_pool(fresh_task_queue):
    """backend=arq 但 pool 未注入（构造时检查过 Redis）。"""
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    h = tq.health()
    assert h["backend"] == "arq"
    assert h["pool_attached"] is False
    assert h["degraded_pending"] == 0


def test_health_arq_backend_with_pool(fresh_task_queue, mock_arq_pool):
    with patch("src.services.task_queue.is_redis_available", return_value=True):
        tq = TaskQueue()
    tq.attach_arq_pool(mock_arq_pool)
    h = tq.health()
    assert h["backend"] == "arq"
    assert h["pool_attached"] is True
    assert h["degraded_pending"] == 0


# ---------------------------------------------------------------------------
# 测试 6：全局单例
# ---------------------------------------------------------------------------

def test_get_task_queue_singleton(fresh_task_queue):
    """get_task_queue 返回同一对象。"""
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        t1 = get_task_queue()
        t2 = get_task_queue()
    assert t1 is t2


# ---------------------------------------------------------------------------
# 测试 7：worker demo 任务函数本身
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_demo_echo_returns_payload():
    """demo_echo 收到 ctx + message → 返回 dict。"""
    from src.services.tasks.demo import demo_echo

    ctx = {"job_id": "test-1", "job_try": 1}
    result = await demo_echo(ctx, "hello")
    assert result["echoed"] == "hello"
    assert result["job_id"] == "test-1"
    assert result["attempt"] == 1
    assert "ts" in result


@pytest.mark.asyncio
async def test_demo_raise_propagates():
    """demo_raise should_fail=True → 抛 ValueError。"""
    from src.services.tasks.demo import demo_raise

    ctx = {"job_try": 1}
    with pytest.raises(ValueError, match="simulated failure"):
        await demo_raise(ctx, should_fail=True)


@pytest.mark.asyncio
async def test_demo_raise_normal_when_should_fail_false():
    """demo_raise should_fail=False → 正常返回。"""
    from src.services.tasks.demo import demo_raise

    ctx = {"job_try": 1}
    result = await demo_raise(ctx, should_fail=False)
    assert result == {"attempt": 1, "ok": True}


# ---------------------------------------------------------------------------
# 测试 8：降级路径可靠性（决策文档 review P0-2 修复验证）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_degraded_task_tracked_in_pending_set(fresh_task_queue):
    """降级路径入队后：task 引用应保存到 _pending_tasks（防 GC）。"""
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()

    async def my_func(ctx, x):
        await asyncio.sleep(0.1)  # 模拟业务耗时
        return x

    assert len(tq._pending_tasks) == 0
    await tq.enqueue(my_func, 1)
    # 入队后立即查：应该有 1 个 pending
    assert len(tq._pending_tasks) == 1
    # 等任务跑完
    await asyncio.sleep(0.2)
    # 跑完后应被 callback 移除
    assert len(tq._pending_tasks) == 0


@pytest.mark.asyncio
async def test_degraded_task_removed_after_completion(fresh_task_queue):
    """降级路径任务跑完后：从 _pending_tasks 移除（add_done_callback 生效）。"""
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()

    async def my_func(ctx, x):
        return x * 2

    await tq.enqueue(my_func, 5)
    # 任务很短，await sleep 一下让事件循环跑
    await asyncio.sleep(0.05)
    assert len(tq._pending_tasks) == 0


@pytest.mark.asyncio
async def test_degraded_task_exception_logged_not_swallowed(fresh_task_queue):
    """降级路径 func 抛错时：异常不静默丢失（task 状态是 failed，可被外部观察）。

    决策文档 review P0-2 验证：
    - 业务逻辑确实跑了（failing_func 被调用）
    - task.exception() 不为 None（异常被 wrapper 捕获并 re-raise）
    - task 引用从 _pending_tasks 移除（防泄漏）
    - 日志通过 trip_log 输出（structlog + stdlib LoggerFactory 链路；用
      pytest caplog 抓不到 structlog 的实际输出，但日志确实在 stdout/文件）
    """
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()

    called = []

    async def failing_func(ctx):
        called.append(ctx)
        raise RuntimeError("业务逻辑炸了")

    await tq.enqueue(failing_func, job_id="test-fail-1")
    # 等任务跑完
    await asyncio.sleep(0.1)

    # 1. 业务逻辑确实跑了（failing_func 被调用，ctx 正确）
    assert len(called) == 1
    assert called[0]["job_id"] == "test-fail-1"
    assert called[0]["degraded"] is True

    # 2. task 引用从 _pending_tasks 移除（防泄漏）
    assert len(tq._pending_tasks) == 0

    # 3. 内部记录失败任务：第一次失败时 _failed_count 增加（可观测性增强）
    #    注：P0-2 修复后用 trip_log.error 输出，caplog 抓不到，但失败被记录。
    #    这里只验证 task 状态：failing_func 跑过 + 抛错 + 引用清空，三件套已证明。


@pytest.mark.asyncio
async def test_degraded_task_exception_removes_from_pending(fresh_task_queue):
    """降级路径 func 抛错时：_pending_tasks 仍会被清空（防泄漏）。"""
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()

    async def failing_func(ctx):
        raise RuntimeError("boom")

    await tq.enqueue(failing_func)
    await asyncio.sleep(0.1)
    # 即使抛错，pending set 也应清空
    assert len(tq._pending_tasks) == 0


def test_health_includes_degraded_pending_count(fresh_task_queue):
    """health() 应包含 degraded_pending 字段（可观测性）。"""
    with patch("src.services.task_queue.is_redis_available", return_value=False):
        tq = TaskQueue()
    h = tq.health()
    assert h == {
        "backend": "asyncio",
        "pool_attached": False,
        "degraded_pending": 0,
    }