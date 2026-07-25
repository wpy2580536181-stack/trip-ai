"""
arq 接入演练 Demo —— 验证任务队列"入队 → 消费 → 结果"全链路。

用法：
    1) 启动 worker（独立终端）：
       cd trip-backend && .venv/bin/python worker.py
    2) 启动 web（独立终端，可选；不启也能演示入队）：
       cd trip-backend && .venv/bin/python -m src.main
    3) 运行本脚本：
       cd trip-backend && .venv/bin/python scripts/demo_arq_job.py

演示 3 类任务：
  1. demo_echo         —— 基础回显（验证入队/消费）
  2. demo_write_redis  —— 写 Redis（验证 worker 能用项目 redis_client）
  3. demo_raise        —— 故意失败（验证 arq 失败重试 → 死信）

输出格式：
  - 哪些任务被入队（job_id）
  - 哪些任务成功 / 失败 / 死信
  - 推荐：开 worker + 本脚本 → 看到完整消费回执
  - 不开 worker：任务会入队但未消费，可在 Redis CLI 看 `LLEN arq:queue:default`
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.redis_client import init_redis, is_redis_available
from src.services.task_queue import get_task_queue
from src.services.tasks.demo import demo_echo, demo_write_redis, demo_raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("demo_arq")


async def main() -> None:
    """主流程：连接 redis → 入队 3 类任务 → 打印结果。"""
    print("=" * 70)
    print("arq 接入演练 Demo")
    print("=" * 70)

    # ---- 1. 初始化 Redis ----
    await init_redis()
    if not is_redis_available():
        logger.error("Redis 不可用，demo 必须有 Redis。请先 `redis-server` 或启动 docker-compose")
        sys.exit(1)
    logger.info("✓ Redis 已连接")

    # ---- 2. 拿 task_queue 单例（pool 由 web 启动时注入；standalone 模式直接用 arq pool）----
    tq = get_task_queue()
    logger.info("✓ TaskQueue backend=%s, is_arq=%s", tq.backend_type, tq.is_arq)

    # standalone 模式：demo 脚本不在 web 进程里，需要自己创建 arq pool
    if not tq.is_arq:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings
            from src.config.settings import settings
            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            tq.attach_arq_pool(pool)
            logger.info("✓ standalone 模式 arq pool 已创建")
        except Exception as e:
            logger.error("创建 arq pool 失败: %s", e)
            sys.exit(1)

    # ---- 3. 入队 3 个 demo 任务 ----
    print("\n--- 入队 demo 任务 ---")

    job1 = await tq.enqueue(
        demo_echo,
        message="hello arq from M0 demo",
        job_id="demo:echo:001",
    )
    logger.info("[1] demo_echo  → job_id=%s", job1)

    job2 = await tq.enqueue(
        demo_write_redis,
        key="demo:arq:m0",
        value="written by arq worker at " + __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        job_id="demo:write_redis:001",
    )
    logger.info("[2] demo_write_redis → job_id=%s", job2)

    # demo_raise: 应失败 3 次后入死信（验证 max_tries 重试机制）
    job3 = await tq.enqueue(
        demo_raise,
        should_fail=True,
        job_id="demo:raise:001",
    )
    logger.info("[3] demo_raise (预期失败) → job_id=%s", job3)

    # ---- 4. 等待 worker 消费 + 读结果 ----
    print("\n--- 等待 worker 消费（最长 30s）---")
    if tq.is_arq:
        from arq import create_pool
        from arq.connections import RedisSettings
        from src.config.settings import settings

        rs = RedisSettings.from_dsn(settings.redis_url)
        # 用 arq.Job 轮询结果
        from arq.jobs import Job

        async with await create_pool(rs) as pool:
            for label, jid in [("demo_echo", job1), ("demo_write_redis", job2), ("demo_raise", job3)]:
                if jid is None:
                    continue
                job = Job(jid, redis=pool)
                try:
                    result = await job.result(timeout=30)
                    logger.info("[%s] ✓ 完成 → result=%s", label, result)
                except Exception as e:
                    status = await job.status()
                    logger.info("[%s] ✗ 失败（status=%s）→ %s", label, status, e)
    else:
        logger.info("task_queue 走的是 asyncio.create_task 降级，arq 结果查询不可用")

    # ---- 5. 收尾 ----
    print("\n--- 收尾 ---")
    health = tq.health()
    logger.info("TaskQueue health: %s", health)
    logger.info("✓ 演示完成")
    logger.info("提示：在 Redis CLI 跑 `LLEN arq:queue:default` 看队列长度")
    logger.info("     跑 `KEYS arq:result:*` 看已完成任务的结果")
    logger.info("     跑 `KEYS arq:dead_letter:*` 看死信（如有）")


if __name__ == "__main__":
    asyncio.run(main())
