"""M2 业务改造端到端验证 —— 验证 chat_stream 触发 _post_chat_tasks → arq 入队 → worker 消费 → summary_service 写库。

跟 M1 e2e 一样，模拟真实链路：
1. 临时 sqlite DB（`e2e_m2.db`）
2. 启动 worker subprocess（共用同一 DB + Redis）
3. 直接 await TripService().chat_stream(...) 异步生成器（mock 掉 agent 避免 LLM）
4. agent yield 一个 `complete` 事件 → chat_stream 推 `__done__` → 触发 _post_chat_tasks 入队
5. worker 消费 job → 调 summary_service.append_key_decision → 写 conversations.summary
6. e2e 查 conversations.summary 字段验证

真实价值（M1 改进点）：
- M1 e2e 只验证了"业务 API → arq 入队 → worker 同步"链路，没碰 chat 流式
- M2 e2e 完整跑 chat_stream 真实链路（mock agent 但其他全真）
- 验证 _post_chat_tasks 在 chat_stream 内部被触发（不是手动调用）
- 验证 summary_service 真的写库（不是只返回 status）

启动方式：
    cd trip-backend
    .venv/bin/python scripts/e2e_m2_post_chat.py

前置：
- Redis 6379 活着
- worker.py 通过环境变量 DATABASE_URL 连同一个 sqlite 文件
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import pickle
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 强制使用临时 sqlite DB（在 worker 启动前设好，让 worker 也连同一份）
E2E_DIR = Path(__file__).parent
E2E_DB_PATH = E2E_DIR / "e2e_m2.db"
E2E_DB_URL = f"sqlite+aiosqlite:///{E2E_DB_PATH.absolute()}"

# 删旧 db（如果有）
if E2E_DB_PATH.exists():
    E2E_DB_PATH.unlink()

# 设置环境变量（必须早于 src.config.settings 加载）
os.environ["DATABASE_URL"] = E2E_DB_URL
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["TRIP_E2E_MODE"] = "1"  # 标记 e2e 模式

# 把项目根加进 sys.path
PROJECT_ROOT = E2E_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 项目 imports（必须在环境变量设置后）
import redis.asyncio as aioredis
from src.config.settings import settings  # noqa: E402
from src.config.database import init_db, async_session  # noqa: E402
from src.config.redis_client import init_redis, close_redis  # noqa: E402
from src.utils.logger import setup_logging, trip_log  # noqa: E402
from src.models.user import User  # noqa: E402
from src.models.conversation import Conversation  # noqa: E402
from src.models.message import Message  # noqa: E402
from src.services.trip_service import TripService  # noqa: E402
from src.services.task_queue import get_task_queue  # noqa: E402
from src.services.tasks.post_chat import post_chat_followup  # noqa: E402

setup_logging()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

async def wait_for_arq_result(job_id: str, timeout_s: float = 30.0) -> dict | None:
    """等 arq 把 result 落盘到 Redis。

    arq 0.28 result 存储：直接读 `arq:result:{job_id}` key（pickle）。
    """
    r = aioredis.from_url(os.environ["REDIS_URL"])
    try:
        deadline = time.time() + timeout_s
        key = f"arq:result:{job_id}"
        while time.time() < deadline:
            data = await r.get(key)
            if data is not None:
                try:
                    return pickle.loads(data)
                except Exception:
                    return {"_raw_bytes_len": len(data), "_note": "pickle 解析失败但 key 存在"}
            await asyncio.sleep(0.3)
        return None
    finally:
        await r.aclose()


async def create_test_user_and_conversation(suffix: str = "1") -> tuple[int, int]:
    """建一个测试用户 + 1 个对话（带 2 条消息模拟对话历史）。"""
    async with async_session() as session:
        user = User(
            email=f"e2e_m2_{suffix}@test.com",
            username=f"e2e_m2_user_{suffix}",
            password="fake-hash",
        )
        session.add(user)
        await session.flush()
        conv = Conversation(
            user_id=user.id,
            title="E2E M2 test conversation",
        )
        session.add(conv)
        await session.flush()
        # 加 2 条消息让 conversation 有"历史"
        msg1 = Message(
            conversation_id=conv.id,
            role="user",
            content="帮我规划北京 3 天行程",
        )
        msg2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content="好的",
        )
        session.add(msg1)
        session.add(msg2)
        await session.commit()
        await session.refresh(user)
        await session.refresh(conv)
        return user.id, conv.id


async def get_conversation_summary(conv_id: int) -> str | None:
    """查 conversations.summary 字段（验证 worker 写库）。"""
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.id == conv_id)
        )
        conv = result.scalar_one_or_none()
        return conv.summary if conv else None


def start_worker_subprocess() -> subprocess.Popen:
    """启动 worker subprocess（连同一份 sqlite + redis）。"""
    import subprocess
    env = os.environ.copy()
    env["DATABASE_URL"] = E2E_DB_URL
    env["REDIS_URL"] = "redis://localhost:6379"
    return subprocess.Popen(
        [str(PROJECT_ROOT / ".venv/bin/python"), "-u", "worker.py"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

import subprocess  # noqa: E402  上面用了，import 放这里避免全局重排


async def scenario_planning(user_id: int, conv_id: int, worker: subprocess.Popen) -> None:
    """场景 1：规划请求 → compress + decision 都被执行。

    验证：
    1. arq 入队（job_id `post_chat:followup:{conv_id}` 存在）
    2. worker 消费（arq:result: 出现且 compressed=True, decision_recorded=True）
    3. summary_service 写库（conversations.summary 包含 "用户发起行程规划"）
    """
    trip_log.info("scenario_planning_start", conv_id=conv_id)

    # mock agent_engine.chat：让 chat_stream 内部 agent 直接 yield complete 事件
    async def mock_chat(*args, **kwargs):
        on_event = kwargs["on_event"]
        await on_event({"type": "complete", "content": "好的，我来帮你规划 3 天北京行程"})

    # init arq pool
    from arq import create_pool
    from arq.connections import RedisSettings
    pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
    get_task_queue().attach_arq_pool(pool)

    # 跑 chat_stream（不调真实 agent）
    # ⚠️ patch 路径关键：trip_service 顶部 `from src.services.agent.agent_engine import get_agent_engine`
    # 已在 import-time 把引用绑到 trip_service 模块自己的名字空间。
    # patch `src.services.agent.agent_engine.get_agent_engine` 不会影响 trip_service 的引用。
    # 必须 patch `src.services.trip_service.get_agent_engine` 才生效。
    with patch("src.services.trip_service.get_agent_engine") as mock_engine:
        mock_engine.return_value.chat = mock_chat
        svc = TripService()
        events = []
        async for event in svc.chat_stream(
            user_id=user_id,
            message="帮我规划北京 3 天行程",
            conversation_id=conv_id,
        ):
            events.append(event)
            if event.get("type") == "complete":
                break

    trip_log.info("chat_stream_completed", events=len(events), last=events[-1])

    # 验证 1：arq job 真的入队
    job_id = f"post_chat:followup:{conv_id}"
    trip_log.info("waiting_for_arq_result", job_id=job_id)
    raw_result = await wait_for_arq_result(job_id, timeout_s=30.0)
    assert raw_result is not None, f"❌ arq result 未落盘: job_id={job_id}"
    # arq 0.28 result 格式：{"t": ..., "f": ..., "a": ..., "k": ..., "et": ..., "s": bool,
    #                          "r": <actual_return_value>, ...}
    # 真正的函数返回值在 "r" 字段
    result = raw_result.get("r") if isinstance(raw_result, dict) else raw_result
    trip_log.info("arq_result_received", raw=raw_result, actual=result)
    assert result.get("compressed") is True, f"❌ compressed 应为 True: {result}"
    assert result.get("decision_recorded") is True, f"❌ decision_recorded 应为 True: {result}"
    assert result.get("decision_skipped") is False, f"❌ decision_skipped 应为 False: {result}"
    assert result.get("conversation_id") == conv_id, f"❌ conversation_id 不匹配: {result}"

    # 验证 2：summary_service 真的写库
    summary = await get_conversation_summary(conv_id)
    trip_log.info("summary_after_worker", summary=summary)
    assert summary is not None, f"❌ conversations.summary 仍为 None（worker 没写库）"
    assert "用户发起行程规划" in summary, f"❌ summary 不包含决策文本: {summary}"
    assert "帮我规划北京 3 天行程" in summary, f"❌ summary 不包含用户消息: {summary}"

    trip_log.info("scenario_planning_passed", conv_id=conv_id)


async def scenario_non_planning(user_id: int, conv_id: int) -> None:
    """场景 2：非规划请求 → 只压缩，不记录决策。

    验证：
    1. arq result：decision_recorded=False, decision_skipped=True
    2. conversations.summary 没被追加决策文本
    """
    trip_log.info("scenario_non_planning_start", conv_id=conv_id)

    # 同样 mock agent
    async def mock_chat(*args, **kwargs):
        on_event = kwargs["on_event"]
        await on_event({"type": "complete", "content": "ok"})

    with patch("src.services.trip_service.get_agent_engine") as mock_engine:
        mock_engine.return_value.chat = mock_chat
        svc = TripService()
        async for event in svc.chat_stream(
            user_id=user_id,
            message="hello",
            conversation_id=conv_id,
        ):
            if event.get("type") == "complete":
                break

    job_id = f"post_chat:followup:{conv_id}"
    raw_result = await wait_for_arq_result(job_id, timeout_s=30.0)
    assert raw_result is not None, f"❌ arq result 未落盘: job_id={job_id}"
    result = raw_result.get("r") if isinstance(raw_result, dict) else raw_result
    trip_log.info("arq_result_received", raw=raw_result, actual=result)
    assert result.get("compressed") is True, f"❌ compressed 应为 True: {result}"
    assert result.get("decision_recorded") is False, f"❌ decision_recorded 应为 False: {result}"
    assert result.get("decision_skipped") is True, f"❌ decision_skipped 应为 True: {result}"

    # 验证 2：summary 没被追加决策文本
    summary = await get_conversation_summary(conv_id)
    trip_log.info("summary_after_worker", summary=summary)
    if summary:
        assert "用户发起行程规划" not in summary, f"❌ 非规划请求不应追加决策: {summary}"
    # summary 为 None 也算通过（非规划 + 消息少不触发压缩是正常）

    trip_log.info("scenario_non_planning_passed", conv_id=conv_id)


async def main():
    print("=" * 70)
    print("M2 e2e 验证 —— chat_stream 触发 _post_chat_tasks → arq → worker → DB")
    print("=" * 70)

    # 1. 检查前置
    print("\n[Step 1] 检查环境")
    r = aioredis.from_url(os.environ["REDIS_URL"])
    if not await r.ping():
        print("❌ Redis 6379 不通")
        return
    print("✓ Redis 6379 PONG")
    await r.aclose()

    # 2. init DB + Redis
    print("\n[Step 2] init DB + Redis")
    # init_db 只验证连接不建表；这里手动 Base.metadata.create_all 建全部表
    from src.models.base import Base
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(E2E_DB_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print(f"✓ DB 建表完毕：{E2E_DB_PATH}")
    await init_db()
    print(f"✓ DB 初始化完毕：{E2E_DB_PATH}")
    await init_redis()
    print("✓ Redis client 初始化完毕")

    # 3. 创建测试数据
    print("\n[Step 3] 创建测试数据")
    user_id_planning, conv_id_planning = await create_test_user_and_conversation(suffix="planning")
    # 非规划场景用不同的 user
    user_id_non, conv_id_non_planning = await create_test_user_and_conversation(suffix="non")
    print(f"✓ 创建 2 个 user + 2 个 conversation")

    # 4. 启动 worker
    print("\n[Step 4] 启动 worker subprocess")
    worker = start_worker_subprocess()
    print(f"✓ Worker PID={worker.pid} 启动")
    # 等 worker 启动完成（健康检查 + connect redis）
    await asyncio.sleep(3)

    try:
        # 5. 场景 1：规划请求
        print("\n[Step 5] 场景 1：规划请求")
        await scenario_planning(user_id_planning, conv_id_planning, worker)
        print("✓ 场景 1 通过：compress + decision 都被执行，写库正确")

        # 6. 场景 2：非规划请求
        print("\n[Step 6] 场景 2：非规划请求")
        await scenario_non_planning(user_id_non, conv_id_non_planning)
        print("✓ 场景 2 通过：只 compress，decision 跳过")

        print("\n" + "=" * 70)
        print("✅ 全部 2 个 e2e 场景通过！")
        print("=" * 70)
    finally:
        # 7. 收尾
        print("\n[Step 7] 收尾")
        worker.terminate()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
        print("✓ Worker 关闭")
        await close_redis()
        # 删测试 db
        if E2E_DB_PATH.exists():
            E2E_DB_PATH.unlink()
            print(f"✓ 清理 {E2E_DB_PATH.name}")
        # 清理 arq 测试残留
        r = aioredis.from_url(os.environ["REDIS_URL"])
        keys = await r.keys("arq:result:*")
        if keys:
            await r.delete(*keys)
            print(f"✓ 清理 {len(keys)} 个 arq result keys")
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
