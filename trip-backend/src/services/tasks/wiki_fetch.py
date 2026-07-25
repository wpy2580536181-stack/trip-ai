"""arq worker 任务 —— 按城市抓取维基百科词条（文本层 ETL 异步化）。

改造动机（决策文档 §3.3 / M3-A）：
- 原 fetch_wiki.py main_async 用 `for city in city_spots: await fetch_city(...)` 串行跨城
  （一城抓完才下一城）。MySQL 真实景点 30792 个 / 153 城 → 即便每城内 8 并发，跨城串行
  也是大瓶颈。
- 改为入队：主进程遍历城市入队（< 5ms/城），worker 并发消费 → 跨城也并行。
- 收益：① 失败可重试（单城粒度）② 断点续跑（--skip-existing 主进程预过滤）
  ③ 多机协同（job 在 Redis 列表里，多机 worker 自动分摊）④ 进度可查（arq:result:*）

设计要点：
- 复用 scripts/fetch_wiki.fetch_city 业务逻辑（不重复实现信号量 + 3 段兜底查询）
- worker 端自己从 MySQL 查该城所有 spots（避免传大 list 序列化）—— MySQL 查询 ~10ms
- 写文件路径：worker 端用 fetch_wiki.WIKI_RAW_DIR 常量（与原脚本一致）
- 失败抛错让 arq 决策（worker.py max_tries=1 → 入死信可查）
- 默认 concurrency=8（保留 49min→8min 的并发上限，避免代理连接堆积）
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 在 worker 进程顶部 import 全部 model，确保 SQLAlchemy mapper 完整初始化
# （避免 User→TokenUsageLog 关系链断裂导致 InvalidRequestError，参考 conftest.py）
import src.models.user  # noqa: F401
import src.models.conversation  # noqa: F401
import src.models.message  # noqa: F401
import src.models.trip  # noqa: F401
import src.models.spot  # noqa: F401
import src.models.spot_doc  # noqa: F401
import src.models.password_reset  # noqa: F401
import src.models.role  # noqa: F401
import src.models.feedback  # noqa: F401
import src.models.agent_step  # noqa: F401
import src.models.token_usage_log  # noqa: F401


async def fetch_city_wiki(
    ctx: Optional[dict],
    city: str,
    lang: str = "zh",
    limit: Optional[int] = None,
    sleep: float = 0.02,
    concurrency: int = 8,
    use_wikidata: bool = True,
    max_candidates: int = 3,
    from_mysql: bool = True,
) -> dict:
    """按城市抓取维基词条（arq worker 任务）。

    复用 scripts/fetch_wiki.fetch_city 的核心抓取逻辑（信号量 + 3 段兜底查询），
    自己从 MySQL 或快照文件读该城所有 spots，写 wiki_raw/{city}.json。

    Args:
        ctx: arq 注入的上下文（含 job_id / job_try）；降级路径为 None 时构造 fake ctx
        city: 城市名（与 Spot.city 字段匹配；snapshot 模式时也用作文件名）
        lang: 维基语言（"zh" | "en"）
        limit: 每城最多抓取 N 个景点（抽样验证用）
        sleep: 每任务完成后额外间隔（秒）
        concurrency: 并发请求数（**默认 8**——保留 49min→8min 的并发上限，避免代理连接堆积）
        use_wikidata: 是否启用 Wikidata 实体检索兜底
        max_candidates: 模糊检索时返回的候选数
        from_mysql: True 从 MySQL 查 spots；False 从 data/spots/{city}.json 快照读

    Returns:
        {"city": str, "fetched": int, "written_to": str | None,
         "source": "mysql" | "snapshot", "total_spots": int,
         "attempt": int}

    Raises:
        Exception: fetch_city 内部异常 / DB 连接异常 → arq 捕获并入死信
    """
    # 兼容降级路径：ctx 为 None 时构造 fake ctx
    if ctx is None:
        ctx = {"job_id": None, "job_try": 1, "degraded": True}

    attempt = ctx.get("job_try", 1)

    # 懒导入：避免 import-time 把整个 scripts 链路 + MySQL 拉起来
    from scripts.fetch_wiki import fetch_city, WIKI_RAW_DIR, SPOTS_DIR

    # 1. 加载该城的 spots
    if from_mysql:
        from sqlalchemy import select
        from src.config.database import async_session
        from src.models.spot import Spot

        async with async_session() as db:
            q = select(Spot.name).where(
                Spot.city == city,
                Spot.name.isnot(None),
                Spot.name != "",
            )
            rows = (await db.execute(q)).all()
        spots = [{"name": r[0], "city": city} for r in rows]
        source = "mysql"
    else:
        snapshot_path = os.path.join(SPOTS_DIR, city + ".json")
        with open(snapshot_path, "r", encoding="utf-8") as fh:
            spots = json.load(fh)
        source = "snapshot"

    if not spots:
        logger.warning(
            "[fetch_city_wiki] no spots city=%s source=%s", city, source,
        )
        return {
            "city": city,
            "fetched": 0,
            "written_to": None,
            "source": source,
            "total_spots": 0,
            "skipped_reason": "no_spots",
            "attempt": attempt,
        }

    logger.info(
        "[fetch_city_wiki] start city=%s source=%s total_spots=%d limit=%s attempt=%s",
        city, source, len(spots), limit, attempt,
    )

    # 2. 调 fetch_city 业务逻辑
    results = await fetch_city(
        city=city,
        spots=spots,
        lang=lang,
        limit=limit,
        sleep=sleep,
        concurrency=concurrency,
        use_wikidata=use_wikidata,
        max_candidates=max_candidates,
    )

    # 3. 写文件（跟原 fetch_wiki.py main_async 行为一致）
    out_path = None
    if results:
        os.makedirs(WIKI_RAW_DIR, exist_ok=True)
        out_path = os.path.join(WIKI_RAW_DIR, city + ".json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)

    logger.info(
        "[fetch_city_wiki] done city=%s fetched=%d/%d written_to=%s attempt=%s",
        city, len(results), len(spots), out_path, attempt,
    )
    return {
        "city": city,
        "fetched": len(results),
        "written_to": out_path,
        "source": source,
        "total_spots": len(spots),
        "attempt": attempt,
    }
