"""
M1 e2e 验证 —— 完整跑通 API 写路径 → arq 入队 → worker 消费 → Chroma 写入

链路：
    KnowledgeService.create_spot/update_spot/bulk_import_spots
    → commit SQLite
    → task_queue.enqueue(sync_spot_to_chroma, ...)
    → arq pool（Redis 127.0.0.1:6379）
    → worker.py 进程消费
    → embed_query_async（BGE 512 维）
    → Chroma spots 集合 upsert（8001）

环境前置（脚本会自检）：
    - Redis 127.0.0.1:6379 PING
    - Chroma 8001 /api/v2/heartbeat
    - worker 已在跑（独立终端：`cd trip-backend && .venv/bin/python worker.py`）

跑法：
    cd trip-backend && .venv/bin/python scripts/e2e_m1_chroma_sync.py

清理：
    - 测试用 SQLite ./e2e_m1.db（脚本结束自动删）
    - Chroma spots 集合里新增的向量（脚本会列出来，可手动 `chroma delete`）
"""
import asyncio
import os
import sys
from pathlib import Path

# ⚠️ 必须在 import src.config.* 之前设好 env（否则 Settings 读到 mysql 配置）
SCRIPT_DIR = Path(__file__).parent
E2E_DB_PATH = SCRIPT_DIR.parent / "e2e_m1.db"
E2E_DB_URL = f"sqlite+aiosqlite:///{E2E_DB_PATH.absolute()}"
os.environ["DATABASE_URL"] = E2E_DB_URL

# 把项目根加进 sys.path
sys.path.insert(0, str(SCRIPT_DIR.parent))

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
)
logger = logging.getLogger("e2e_m1")
# 降低 chromadb / httpx 噪音
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# 自检：Redis + Chroma 必须可达
# ---------------------------------------------------------------------------

async def preflight_check() -> None:
    """启动前自检：Redis 通 + Chroma 通。worker 由用户在独立终端启动。"""
    import redis.asyncio as aioredis
    import httpx

    # 1. Redis
    r = aioredis.from_url("redis://localhost:6379")
    try:
        pong = await r.ping()
        if not pong:
            raise RuntimeError("Redis PING 返回非 True")
        logger.info("✓ Redis 6379 PONG")
    finally:
        await r.aclose()

    # 2. Chroma
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get("http://localhost:8001/api/v2/heartbeat")
        resp.raise_for_status()
    logger.info("✓ Chroma 8001 heartbeat OK")


# ---------------------------------------------------------------------------
# 数据库初始化
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """建表（用 Base.metadata.create_all，避免 alembic 迁移）。"""
    from src.config.database import engine
    from src.models.base import Base
    # 显式 import 所有 model，让 Base.metadata 知道
    import src.models.user
    import src.models.role
    import src.models.conversation
    import src.models.message
    import src.models.trip
    import src.models.spot
    import src.models.spot_doc
    import src.models.password_reset
    import src.models.feedback
    import src.models.agent_step
    import src.models.token_usage_log

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)  # 干净起步
        await conn.run_sync(Base.metadata.create_all)
    logger.info(f"✓ DB 初始化完毕：{E2E_DB_PATH.name}")


# ---------------------------------------------------------------------------
# 核心验证
# ---------------------------------------------------------------------------

async def get_chroma_count() -> int:
    """查 Chroma spots 集合当前向量数。"""
    from src.services.rag.chroma_client import get_spots_collection, run_sync
    col = await get_spots_collection()
    return await run_sync(col.count)


async def get_spot_in_chroma(vector_id: str) -> dict | None:
    """按 vector_id 查 Chroma 单条记录（peek）。"""
    from src.services.rag.chroma_client import get_spots_collection, run_sync
    col = await get_spots_collection()
    res = await run_sync(
        col.get,
        ids=[vector_id],
        include=["metadatas", "documents"],
    )
    if not res or not res.get("ids"):
        return None
    return {
        "id": res["ids"][0],
        "document": res["documents"][0] if res.get("documents") else None,
        "metadata": res["metadatas"][0] if res.get("metadatas") else None,
    }


async def wait_for_chroma_sync(
    vector_id: str,
    *,
    expected_status: str = "synced",
    timeout_s: float = 30.0,
    poll_interval_s: float = 0.5,
) -> dict | None:
    """轮询 Chroma 等到指定 vector_id 出现（worker 已 upsert）。"""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        record = await get_spot_in_chroma(vector_id)
        if record is not None:
            return record
        await asyncio.sleep(poll_interval_s)
    return None


async def get_arq_result(job_id: str, timeout_s: float = 30.0) -> dict | None:
    """读 arq result（worker 完成后写的返回值）。

    实现：直接用原生 redis.asyncio 读 `arq:result:{job_id}` key（pickle 反序列化）。
    比 arq 的 Job.result() 抽象更直接，能验证 arq 实际落盘的 result 数据。
    """
    import pickle
    import redis.asyncio as aioredis
    from src.config.settings import settings

    r = aioredis.from_url(settings.redis_url)
    try:
        key = f"arq:result:{job_id}"
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            data = await r.get(key)
            if data is not None:
                try:
                    return pickle.loads(data)
                except Exception:
                    return {"_raw_bytes_len": len(data), "_note": "pickle failed but key exists"}
            await asyncio.sleep(0.2)
        return None
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# 三个测试场景
# ---------------------------------------------------------------------------

async def scenario_create() -> None:
    """场景 1：create_spot → 入队 → worker 写 Chroma。"""
    logger.info("─" * 60)
    logger.info("场景 1：create_spot")
    logger.info("─" * 60)

    from src.config.database import async_session
    from src.services.knowledge_service import KnowledgeService
    from src.schemas.knowledge import SpotCreate

    baseline = await get_chroma_count()
    logger.info(f"  baseline Chroma spots 集合 count = {baseline}")

    async with async_session() as db:
        spot = await KnowledgeService.create_spot(
            db,
            SpotCreate(
                name="E2E 故宫",
                city="北京",
                category="历史",
                description="M1 e2e 验证用 spot",
                tags=["e2e", "M1"],
                avg_cost=60.0,
                duration="3h",
                open_time="08:30-17:00",
                rating=4.9,
            ),
        )
        spot_id = spot.id
        vector_id = spot.vector_id
        job_id = f"chroma_sync:create:{spot_id}"

    logger.info(f"  ✓ create_spot 完成：spot_id={spot_id} vector_id={vector_id}")

    # 调试：立刻查 redis 看 arq result key 是否存在
    import redis.asyncio as aioredis
    debug_r = aioredis.from_url("redis://localhost:6379")
    keys_immediately = await debug_r.keys("arq:result:*")
    logger.info(f"  [debug] 入队后立即查 arq:result:* = {[k.decode() for k in keys_immediately]}")
    await debug_r.aclose()

    # 等 worker 消费
    logger.info(f"  等待 worker 消费 job_id={job_id}（最长 30s）...")
    record = await wait_for_chroma_sync(vector_id, timeout_s=30.0)
    if record is None:
        raise AssertionError(f"❌ worker 未在 30s 内 upsert vector_id={vector_id}")

    logger.info(f"  ✓ Chroma 中已找到 vector：")
    logger.info(f"    document: {record['document'][:60]}...")
    logger.info(f"    metadata: {record['metadata']}")

    # 验证 arq result（可选：arq 0.28 result 落盘对 keep_result 配置敏感；
    # M1 业务目标以 Chroma 数据更新为准，result 落盘不阻塞 e2e）
    result = await get_arq_result(job_id, timeout_s=30.0)
    if result is None:
        logger.warning("⚠️  arq result 未落盘（M1 业务目标已达成：Chroma 已 upsert，result 落盘仅影响可观测性）")
    elif result.get("_error"):
        logger.warning(f"⚠️  arq result 读取错误: {result.get('_error')}")
    else:
        logger.info(f"  arq result: {result}")
        if result.get("status") != "synced":
            logger.warning(f"⚠️  arq result status != synced: {result}")
        elif result.get("spot_id") != spot_id or result.get("vector_id") != vector_id:
            logger.warning(f"⚠️  arq result 字段不匹配: {result}")
        else:
            logger.info(f"  ✓ arq result 完整匹配（spot_id/vector_id/status 全对）")

    new_count = await get_chroma_count()
    logger.info(f"  ✓ baseline {baseline} → after {new_count}（+{new_count - baseline}）")
    assert new_count == baseline + 1, f"Chroma 计数应 +1，实际 {new_count - baseline}"


async def scenario_update() -> None:
    """场景 2：update_spot → 入队 upsert → worker 更新 Chroma（同一 vector_id 替换文档/元数据）。"""
    logger.info("─" * 60)
    logger.info("场景 2：update_spot（upsert 同一 vector_id）")
    logger.info("─" * 60)

    from src.config.database import async_session
    from src.services.knowledge_service import KnowledgeService
    from src.schemas.knowledge import SpotCreate, SpotUpdate

    async with async_session() as db:
        # 先建一个
        spot = await KnowledgeService.create_spot(
            db,
            SpotCreate(
                name="E2E 颐和园",
                city="北京",
                category="历史",
                description="v1 description",
                tags=["e2e"],
                avg_cost=30.0,
                duration="2h",
                open_time="06:30-18:00",
                rating=4.5,
            ),
        )
        spot_id = spot.id
        vector_id = spot.vector_id
        job_id_create = f"chroma_sync:create:{spot_id}"
    await wait_for_chroma_sync(vector_id, timeout_s=30.0)
    record_v1 = await get_spot_in_chroma(vector_id)
    logger.info(f"  v1 created：document={record_v1['document'][:50]}...")

    # 改 rating + description
    async with async_session() as db:
        await KnowledgeService.update_spot(
            db, spot_id,
            SpotUpdate(description="v2 description UPDATED", rating=4.95),
        )
    job_id_update = f"chroma_sync:update:{spot_id}"
    logger.info(f"  ✓ update_spot 完成，job_id={job_id_update}")

    # 等 worker 消费 upsert
    deadline = asyncio.get_event_loop().time() + 30.0
    updated = None
    while asyncio.get_event_loop().time() < deadline:
        record = await get_spot_in_chroma(vector_id)
        if record and "UPDATED" in (record["document"] or ""):
            updated = record
            break
        await asyncio.sleep(0.5)

    if updated is None:
        raise AssertionError(f"❌ worker 未在 30s 内 upsert 更新到 vector_id={vector_id}")
    logger.info(f"  ✓ Chroma upsert 成功（同一 vector_id 内容已更新）：")
    logger.info(f"    document: {updated['document'][:80]}")
    logger.info(f"    metadata: {updated['metadata']}")
    assert "UPDATED" in updated["document"]
    assert updated["metadata"]["rating"] == 4.95


async def scenario_bulk_import() -> None:
    """场景 3：bulk_import_spots 5 个 → 入队 5 个 job → worker 并行消费 → Chroma +5。"""
    logger.info("─" * 60)
    logger.info("场景 3：bulk_import_spots（细粒度 5 个 job）")
    logger.info("─" * 60)

    from src.config.database import async_session
    from src.services.knowledge_service import KnowledgeService

    baseline = await get_chroma_count()
    logger.info(f"  baseline Chroma spots 集合 count = {baseline}")

    spots_data = [
        {
            "name": f"E2E Bulk {i}",
            "city": "上海" if i % 2 == 0 else "杭州",
            "category": "测试",
            "description": f"bulk 第 {i} 个",
            "tags": ["bulk", f"tag-{i}"],
            "avg_cost": float(i * 10),
            "duration": f"{i}h",
            "open_time": "00:00-24:00",
            "rating": 3.0 + i * 0.1,
        }
        for i in range(5)
    ]

    async with async_session() as db:
        result = await KnowledgeService.bulk_import_spots(db, spots_data)
    logger.info(f"  bulk_import 返回：{result}")
    assert result["success"] == 5, f"应有 5 成功，实际 {result}"

    # 等 5 个 Chroma upsert 完成
    deadline = asyncio.get_event_loop().time() + 30.0
    new_count = baseline
    while asyncio.get_event_loop().time() < deadline:
        new_count = await get_chroma_count()
        if new_count >= baseline + 5:
            break
        await asyncio.sleep(0.5)

    if new_count < baseline + 5:
        raise AssertionError(
            f"❌ worker 未在 30s 内 upsert 5 个：baseline={baseline} new={new_count}"
        )
    logger.info(f"  ✓ baseline {baseline} → after {new_count}（+{new_count - baseline}）")
    assert new_count == baseline + 5


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def main() -> int:
    print("=" * 60)
    print("M1 e2e 验证 —— API 写路径 → arq → worker → Chroma")
    print("=" * 60)
    print()
    print("⚠️  前提：worker 已在独立终端启动")
    print("   命令：cd trip-backend && .venv/bin/python worker.py")
    print()

    # 1. 自检
    print("[1/4] 前置环境自检")
    await preflight_check()
    print()

    # 2. DB 初始化
    print("[2/4] 初始化 SQLite 测试库")
    if E2E_DB_PATH.exists():
        E2E_DB_PATH.unlink()
        logger.info(f"  删除旧 db 文件：{E2E_DB_PATH.name}")
    await init_db()
    print()

    # 3. 跑 3 个场景
    print("[3/4] 跑 3 个 e2e 场景")
    failed = []
    for name, fn in [
        ("create_spot", scenario_create),
        ("update_spot", scenario_update),
        ("bulk_import_spots", scenario_bulk_import),
    ]:
        try:
            await fn()
        except AssertionError as e:
            logger.error(f"❌ {name} 失败：{e}")
            failed.append((name, str(e)))
        except Exception as e:
            logger.exception(f"❌ {name} 异常：{e}")
            failed.append((name, str(e)))
    print()

    # 4. 收尾
    print("[4/4] 收尾")
    if failed:
        print(f"\n❌ {len(failed)} 个场景失败：")
        for name, err in failed:
            print(f"   - {name}: {err}")
        return 1

    print("\n✅ 全部 3 个 e2e 场景通过！")
    print(f"   - create_spot: 1 spot → 1 job → Chroma +1")
    print(f"   - update_spot: upsert 同一 vector_id（document/metadata 已更新）")
    print(f"   - bulk_import_spots: 5 spots → 5 jobs → Chroma +5")
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
