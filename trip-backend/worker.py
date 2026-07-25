"""arq Worker 启动入口。

启动命令：
    cd trip-backend && .venv/bin/python worker.py

WorkerSettings 是 arq 的约定入口（arq 启动时 import 该类）。

日志：复用项目的 structlog 配置（src/utils/logger.py），与 web 进程
输出格式一致（JSON + 敏感字段脱敏）。worker 进程通过
trip_log / arq.worker logger 记录生命周期与任务执行。
"""
from __future__ import annotations

import asyncio
import sys

from arq.connections import RedisSettings
from arq.worker import func

from src.config.settings import settings
from src.utils.logger import setup_logging, trip_log
from src.services.tasks.demo import demo_echo, demo_write_redis, demo_raise
from src.services.tasks.chroma_sync import sync_spot_to_chroma
from src.services.tasks.post_chat import post_chat_followup
from src.services.tasks.wiki_fetch import fetch_city_wiki

# arq 0.28 keep_result 是 Function 级别（不是 WorkerSettings 级别），
# 必须用 func() wrapper 显式配；直接传函数对象会让 keep_result 失效，
# 表现是 result 不写盘（Job.result() 报 "Not waiting for job result"）。
DEFAULT_KEEP_RESULT_S = 3600  # 1 小时


# ---------------------------------------------------------------------------
# 生命周期钩子
# ---------------------------------------------------------------------------

async def startup(ctx: dict) -> None:
    """worker 启动时：初始化 redis_client（与 web 进程共用同一 Redis）。"""
    from src.config.redis_client import init_redis

    await init_redis()
    trip_log.info("arq_worker_startup_complete", redis_url=settings.redis_url)


async def shutdown(ctx: dict) -> None:
    """worker 关闭时：清理 redis 连接。"""
    from src.config.redis_client import close_redis

    await close_redis()
    trip_log.info("arq_worker_shutdown_complete")


# ---------------------------------------------------------------------------
# Worker 配置
# ---------------------------------------------------------------------------

class WorkerSettings:
    """arq worker 配置。

    字段说明（arq 0.28）：
    - redis_settings: 连接项目 Redis（与 web 进程共用）
    - functions: 注册可被入队调用的任务函数。**注意**：`keep_result` 在 arq 0.28 是
      Function 级别（不是 WorkerSettings 级别），必须用 `arq.func(fn, keep_result=...)`
      wrapper 显式配。WorkerSettings.keep_result 字段在 0.28 不生效。
    - on_startup / on_shutdown: 生命周期钩子
    - max_tries: 任务失败重试次数（arq 默认指数退避 1s/2s/4s/...）。
      **本项目 max_tries=1**：chroma_client 冷却期 60s 远长于重试间隔，
      多次重试全在冷却期内被短路，1 次失败入死信更可观测（决策文档 review P0-1）。
    - job_timeout: 单个任务超时（秒）
    - health_check_interval: worker 心跳上报间隔
    """

    redis_settings: RedisSettings = RedisSettings.from_dsn(settings.redis_url)

    # 注册任务：
    # - demo（M0 演示）
    # - sync_spot_to_chroma（M1：API 写路径异步 embedding 同步）
    # - post_chat_followup（M2：对话结束后摘要压缩 + 关键决策记录）
    # - fetch_city_wiki（M3-A：维基抓取断点续跑 / 多机协同）
    # 注意：每个函数用 arq.func() wrapper 配 keep_result（arq 0.28 Function 级别配置）
    functions = [
        func(demo_echo, keep_result=DEFAULT_KEEP_RESULT_S),
        func(demo_write_redis, keep_result=DEFAULT_KEEP_RESULT_S),
        func(demo_raise, keep_result=DEFAULT_KEEP_RESULT_S),
        func(sync_spot_to_chroma, keep_result=DEFAULT_KEEP_RESULT_S),
        func(post_chat_followup, keep_result=DEFAULT_KEEP_RESULT_S),
        func(fetch_city_wiki, keep_result=DEFAULT_KEEP_RESULT_S),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # 任务失败重试策略（决策文档 review 报告 P0-1 修复）：
    #   max_tries=1（不重试）—— 因为 chroma_client._CHROMA_DOWN_TTL=60s 冷却期
    #   跟 arq 默认重试间隔（1s+2s+4s=7s）不兼容：3 次重试全在冷却期内被短路，
    #   "假重试"反而比"1 次失败入死信"更危险（看起来在重试，实际无效）。
    #   改为 1 次失败 → 任务入 arq 死信（arq:dead_letter:*） → 由外部告警/对账
    #   脚本（如 scripts/chroma_reindex.py --force）兜底，可观测性更强。
    max_tries = 1

    # 单任务超时 5 分钟（BGE embedding + Chroma RPC 实际约 15-20s）
    job_timeout = 300

    # worker 心跳 30s 一次
    health_check_interval = 30

    # 注：keep_result 在 arq 0.28 是 Function 级别，必须用 arq.func() wrapper
    # 在 functions 列表里给每个任务单独配（见上）。这里仅作文档说明。


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    """worker 主入口：先配日志再起 arq run_worker。"""
    # 复用项目 structlog 配置（JSON 输出 + 敏感字段脱敏）
    log_level = "DEBUG" if settings.node_env == "development" else "INFO"
    setup_logging(level=log_level)

    trip_log.info(
        "arq_worker_starting",
        node_env=settings.node_env,
        log_level=log_level,
        functions=[f.name for f in WorkerSettings.functions],
        max_tries=WorkerSettings.max_tries,
        job_timeout=WorkerSettings.job_timeout,
    )

    from arq import run_worker
    asyncio.run(run_worker(WorkerSettings))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        trip_log.info("arq_worker_interrupted_by_user")
        sys.exit(0)
    except Exception as e:
        trip_log.error("arq_worker_fatal", error=str(e), error_type=type(e).__name__)
        sys.exit(1)
