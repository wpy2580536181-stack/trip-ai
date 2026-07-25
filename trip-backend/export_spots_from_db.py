"""从 MySQL 反向导出最新 spots 到 data/spots/{city}.json。

用途：data/spots/ 里的离线快照已与线上数据库脱节（曾仅 767 条 / 31 城，
而 DB 现已有 30,791 条 / 153 城）。本脚本把 DB 的当前真实状态反向导出，
作为可复现的最新离线快照，字段格式与 seed_spots.py 读取格式对齐。

用法: uv run python export_spots_from_db.py
"""

import asyncio
import json
import shutil
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

BACKEND_ROOT = Path(__file__).parent
SPOTS_DIR = BACKEND_ROOT / "data" / "spots"
ARCHIVE_DIR = BACKEND_ROOT / "data" / f"spots.archive.{date.today().isoformat()}"

# 与 seed_spots.py 读取格式对齐（camelCase 键）
EXPORT_COLUMNS = [
    "name",
    "city",
    "category",
    "description",
    "tags",
    "avg_cost",
    "duration",
    "open_time",
    "rating",
]


def _row_to_spot(row: dict) -> dict:
    """DB 行 -> data/spots 的 camelCase JSON 结构"""
    tags = row.get("tags")
    if isinstance(tags, str):  # 个别驱动返回 JSON 字符串时兜底
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = []
    return {
        "name": row["name"],
        "city": row.get("city") or "未知",
        "category": row.get("category") or "景点",
        "description": row.get("description") or "",
        "tags": tags or [],
        "avgCost": row.get("avg_cost"),
        "duration": row.get("duration"),
        "openTime": row.get("open_time"),
        "rating": row.get("rating"),
    }


async def export_spots():
    db_url = settings.database_url
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)

    engine = create_async_engine(db_url, pool_size=5, max_overflow=10)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 1) 备份现有离线快照（仅首次运行，避免覆盖历史归档）
    if SPOTS_DIR.exists():
        existing = list(SPOTS_DIR.glob("*.json"))
        if existing and not ARCHIVE_DIR.exists():
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            for f in existing:
                shutil.copy2(f, ARCHIVE_DIR / f.name)
            print(f"📦 已备份 {len(existing)} 个旧文件 -> {ARCHIVE_DIR.name}")

    # 2) 查询全部 spots
    cols = ", ".join(EXPORT_COLUMNS)
    async with SessionLocal() as session:
        result = await session.execute(text(f"SELECT {cols} FROM spots"))
        rows = result.mappings().all()

    # 3) 按城市分组
    by_city: dict[str, list[dict]] = {}
    for row in rows:
        spot = _row_to_spot(row)
        by_city.setdefault(spot["city"], []).append(spot)

    # 4) 写出（清旧写新，保证快照与 DB 完全一致）
    SPOTS_DIR.mkdir(parents=True, exist_ok=True)
    for f in SPOTS_DIR.glob("*.json"):
        f.unlink()

    total = 0
    for city, spots in by_city.items():
        spots.sort(key=lambda s: s["name"])
        out = SPOTS_DIR / f"{city}.json"
        out.write_text(
            json.dumps(spots, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        total += len(spots)

    await engine.dispose()

    print(f"\n✅ 导出完成：{total} 条 / {len(by_city)} 个城市")
    print(f"   输出目录：{SPOTS_DIR}")


if __name__ == "__main__":
    asyncio.run(export_spots())
