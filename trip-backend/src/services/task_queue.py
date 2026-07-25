"""任务队列（arq 优先，asyncio.create_task 降级）

设计模式与 src/services/poi_cache.py 双后端一致：
- Redis 可用 → arq 异步任务队列（可靠投递 / 失败重试 / 状态可查）
- Redis 不可用 → asyncio.create_task 内存降级（保留旧行为，绝不抛错给上游）

调用方完全无感：通过 get_task_queue() 单例调用 enqueue() 即可。

arq pool 由 main.py lifespan 初始化后注入到本单例（解耦）。

arq 0.28 用法约定：
- worker 函数签名 `async def func(ctx, *args, **kwargs)`，ctx 由 arq 自动注入
- 入队时用 `enqueue_job('func_name', *args, _job_id=..., **kwargs)`，arq 0.28 接受
  _job_id 作为幂等键（重复入队只执行一次，结果可重读）
- 失败重试：worker.py 配置 max_tries（默认 1，chroma 冷却期不兼容多轮重试）

降级路径可靠性（决策文档 review 报告 P0-2 修复）：
- 任务引用保存到 _pending_tasks 集合（避免 GC）
- 任务异常通过 add_done_callback 提取并 log（绝不静默）
"""
import asyncio
import weakref
from typing import Any, Callable, Optional

from src.config.redis_client import is_redis_available
from src.utils.logger import trip_log


class TaskQueue:
    """任务队列统一接口。

    优先使用 arq（基于 Redis），不可用时降级为 asyncio.create_task。
    上层调用 enqueue() 时无需关心后端类型。
    """

    def __init__(self) -> None:
        # arq pool 由 main.py lifespan 注入；这里只占位
        self._arq_pool: Optional[Any] = None
        # 决定后端类型：Redis 可用且 arq 已装 → arq；否则降级
        if is_redis_available():
            try:
                from arq import create_pool  # noqa: F401  仅验证可导入
                self._backend_type = "arq"
            except ImportError:
                trip_log.warning("task_queue_init", note="arq 未安装，降级为 asyncio")
                self._backend_type = "asyncio"
        else:
            self._backend_type = "asyncio"
        # 降级路径的 task 引用集合：强引用避免 GC（决策文档 review P0-2）
        # 任务完成后通过 add_done_callback 自动移除
        self._pending_tasks: set[asyncio.Task] = set()
        trip_log.info("task_queue_init", backend=self._backend_type)

    @property
    def backend_type(self) -> str:
        return self._backend_type

    @property
    def is_arq(self) -> bool:
        return self._backend_type == "arq" and self._arq_pool is not None

    def attach_arq_pool(self, pool: Any) -> None:
        """由 main.py lifespan 调用，注入 arq pool。

        Args:
            pool: arq.connections.ArqRedis 实例（create_pool 返回值）
        """
        self._arq_pool = pool
        trip_log.info("task_queue_arq_pool_attached")

    async def enqueue(
        self,
        func: Callable,
        *args: Any,
        job_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """入队任务。

        失败静默降级（不抛错给上游）。入队失败时退化为 asyncio.create_task，
        确保业务逻辑至少被触发一次（best-effort 投递）。

        Args:
            func: 要执行的协程函数。worker 端签名应为 `async def func(ctx, *args, **kwargs)`
            *args: 位置参数（传给 worker 函数）
            job_id: 幂等键（可选）。相同 job_id 重复入队只执行一次
            **kwargs: 关键字参数（传给 worker 函数）

        Returns:
            成功入队时返回 job_id（str）；失败/降级时返回 None
        """
        # 路径 1：arq 后端可用 → 可靠投递
        if self.is_arq:
            try:
                job = await self._arq_pool.enqueue_job(
                    func.__name__,
                    *args,
                    _job_id=job_id,
                    **kwargs,
                )
                return job.job_id if job else job_id
            except Exception as e:
                trip_log.warning(
                    "task_queue_arq_enqueue_failed_falling_back",
                    func=func.__name__,
                    job_id=job_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # 继续走降级路径

        # 路径 2：asyncio.create_task 降级（最差也要跑起来）
        # 决策文档 review P0-2 修复：
        #   - worker 函数签名 `async def func(ctx, *args, **kwargs)`，arq 端
        #     会自动注入 ctx。降级路径需构造 fake_ctx 占位。
        #   - 任务引用保存到 _pending_tasks 集合（强引用避免被 GC）
        #   - 异常通过 add_done_callback 提取并 log（绝不静默丢失）
        try:
            fake_ctx = {
                "job_id": job_id,
                "job_try": 1,
                "degraded": True,
            }

            async def _degraded_wrapper():
                # 包一层 try/except 确保异常被记录（即使 callback 漏接）
                try:
                    return await func(fake_ctx, *args, **kwargs)
                except Exception as e:
                    trip_log.error(
                        "task_queue_degraded_task_failed",
                        func=func.__name__,
                        job_id=job_id,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise  # 仍 raise 让 add_done_callback 也能看到

            task = asyncio.create_task(_degraded_wrapper())
            self._pending_tasks.add(task)
            # 任务完成后从集合移除 + 提取异常（防"Task exception was never retrieved"）
            task.add_done_callback(self._on_degraded_task_done)
            return None
        except Exception as e:
            # create_task 本身失败（极少见，事件循环关闭等）
            trip_log.error(
                "task_queue_create_task_failed",
                func=func.__name__,
                job_id=job_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def _on_degraded_task_done(self, task: asyncio.Task) -> None:
        """降级任务完成回调：从 _pending_tasks 移除 + 提取异常。

        决策文档 review P0-2：异常已被 wrapper 内部 try/except log，
        此处的目的是显式 remove + 二次兜底（如果 wrapper 本身有 bug 漏接异常）。
        """
        self._pending_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # wrapper 内部已 log；这里再兜底一次（保险）
            exc = task.exception()
            trip_log.error(
                "task_queue_degraded_task_done_with_exception",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    def health(self) -> dict:
        """健康检查（供 /health/detail 等端点使用）。

        Returns:
            dict: {"backend": "arq" | "asyncio", "pool_attached": bool,
                   "degraded_pending": int（降级路径在飞任务数）}
        """
        return {
            "backend": self._backend_type,
            "pool_attached": self._arq_pool is not None,
            "degraded_pending": len(self._pending_tasks),
        }


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """获取全局 TaskQueue 单例。"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
