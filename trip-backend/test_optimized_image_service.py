#!/usr/bin/env python3
"""
优化后 Amap MCP 图片服务端到端验证

用法：
  cd trip-backend && .venv/bin/python test_optimized_image_service.py
"""

import asyncio
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.services.unsplash_service import _fetch_amap_photo, _clean_amap_keyword
from src.config.settings import settings


# 真实行程中可能出现的名称
REAL_ITINERARY_NAMES = [
    # 景点
    ("故宫博物院", "北京"),
    ("天安门广场", "北京"),
    ("景山公园", "北京"),
    ("八达岭长城", "北京"),
    ("鸟巢", "北京"),
    # 餐饮
    ("全聚德(北京和平门店)", "北京"),
    ("四季民福烤鸭店(呼家楼店)", "北京"),
    ("护国寺小吃", "北京"),
    # 住宿
    ("北京华尔道夫酒店", "北京"),
    ("wohkoon者行孙酒店(北京鸟巢北苑地铁站店)", "北京"),
    # 商圈/休闲
    ("王府井大街", "北京"),
]


async def test_fetch(name: str, city: str) -> dict:
    """测试单个地点的图片查询"""
    try:
        url = await _fetch_amap_photo(city, name)
        return {"name": name, "city": city, "url": url}
    except Exception as e:
        return {"name": name, "city": city, "error": str(e)}


async def test_clean_name():
    """测试 _clean_amap_keyword 效果"""
    test_names = [
        "故宫博物院",
        "全聚德(北京和平门店)",
        "四季民福烤鸭店(呼家楼店)",
        "北京华尔道夫酒店",
        "天安门广场",
    ]
    print("🔧 _clean_amap_keyword 测试:")
    for n in test_names:
        cleaned = _clean_amap_keyword(n)
        print(f"   {n}")
        print(f"   → {cleaned}")
        print()
    print()


async def main():
    print("🔧 检查配置...")
    print(f"   AMAP_MAPS_API_KEY 已配置: {bool(settings.amap_maps_api_key)}")

    # 测试 _clean_name
    await test_clean_name()

    # 启动 MCP server
    from src.services.mcp.amap_client import _ensure_mcp_process, close_mcp_process
    try:
        await _ensure_mcp_process()
        await asyncio.sleep(2)
        print("✅ Amap MCP server 已启动\n")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return

    # 测试所有真实名称
    print("📊 测试真实行程名称图片查询（优化版）")
    print("="*80)

    results = []
    for name, city in REAL_ITINERARY_NAMES:
        r = await test_fetch(name, city)
        results.append(r)

        if r.get("error"):
            print(f"❌ {name}: 错误 {r['error']}")
        elif r.get("url"):
            print(f"✅ {name}")
            print(f"   🖼  {r['url'][:70]}...")
        else:
            print(f"⚠️  {name}: 无图片")

    # 汇总
    total = len(results)
    has_url = sum(1 for r in results if r.get("url"))
    print(f"\n{'='*80}")
    print(f"📊 总计: {has_url}/{total} 有图 ({has_url/total*100:.1f}%)")
    print(f"{'='*80}")

    # 按类型分组
    from collections import defaultdict
    cats = defaultdict(lambda: {"total": 0, "has": 0})
    for r in results:
        if "景点" in r["name"] or any(x in r["name"] for x in ["故宫", "天安门", "景山", "长城", "鸟巢"]):
            cat = "景点"
        elif any(x in r["name"] for x in ["全聚德", "四季民福", "护国寺"]):
            cat = "餐饮"
        elif any(x in r["name"] for x in ["酒店", "住宿"]):
            cat = "住宿"
        else:
            cat = "其他"
        cats[cat]["total"] += 1
        if r.get("url"):
            cats[cat]["has"] += 1

    print("\n按类型:")
    for cat, s in sorted(cats.items()):
        pct = s["has"] / s["total"] * 100 if s["total"] else 0
        print(f"  {cat}: {s['has']}/{s['total']} ({pct:.0f}%)")

    # 清理
    try:
        await close_mcp_process()
        print("\n🧹 MCP server 已关闭")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
