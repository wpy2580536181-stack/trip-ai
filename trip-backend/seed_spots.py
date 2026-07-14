"""种子数据导入脚本。

从 data/spots/ 目录加载 JSON 数据并写入 MySQL + ChromaDB。
用法: uv run python seed_spots.py
"""

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings
from src.models.spot import Spot

SPOTS_DIR = Path(__file__).parent / "data" / "spots"


def _build_embedding_document(spot: dict) -> str:
    """构建用于 embedding 的文档文本（与知识服务保持一致）"""
    tags = " ".join(spot.get("tags", []))
    return f"{spot['city']} {spot['name']} {spot['description']} {tags} {spot['category']}"


async def seed_spots():
    """从 data/spots/*.json 导入景点数据"""
    db_url = settings.database_url
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)

    engine = create_async_engine(db_url)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    json_files = sorted(SPOTS_DIR.glob("*.json"))
    if not json_files:
        print(f"❌ 在 {SPOTS_DIR} 中未找到 JSON 文件")
        return

    total = 0
    async with SessionLocal() as session:
        for fpath in json_files:
            city = fpath.stem
            with open(fpath, encoding="utf-8") as f:
                spots_data = json.load(f)

            count = 0
            for item in spots_data:
                existing = await session.execute(
                    text("SELECT id FROM spots WHERE name = :name AND city = :city"),
                    {"name": item["name"], "city": item.get("city", city)},
                )
                if existing.scalar():
                    continue  # 跳过已存在的

                spot = Spot(
                    name=item["name"],
                    city=item.get("city", city),
                    category=item.get("category", "景点"),
                    description=item.get("description", ""),
                    tags=item.get("tags", []),
                    avg_cost=item.get("avgCost"),
                    duration=item.get("duration"),
                    open_time=item.get("openTime"),
                    rating=item.get("rating"),
                )
                session.add(spot)
                count += 1

            await session.commit()
            total += count
            print(f"  {city}: {count} 条")

    await engine.dispose()
    print(f"\n✅ 导入完成，共 {total} 条新数据")
    print("注意：ChromaDB 向量同步需通过 API 写入时自动完成。")
    print("如需为已有数据同步向量，请通过管理端 API 触发。")

    if not total:
        print("（所有数据已存在，无需导入）")


if __name__ == "__main__":
    asyncio.run(seed_spots())
