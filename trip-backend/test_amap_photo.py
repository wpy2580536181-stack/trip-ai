#!/usr/bin/env python3
"""
测试 Amap MCP maps_text_search 对各类关键词的返回情况

用法：
  cd trip-backend && .venv/bin/python test_amap_photo.py
"""

import asyncio
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings
from src.services.mcp.amap_client import _ensure_mcp_process, call_tool, close_mcp_process


# 测试关键词列表
TEST_QUERIES = [
    # (keywords, city, 期望类型)
    ("故宫博物院", "北京", "景点"),
    ("天安门广场", "北京", "景点"),
    ("全聚德", "北京", "餐饮-品牌"),
    ("全聚德(北京和平门店)", "北京", "餐饮-具体门店"),
    ("四季民福", "北京", "餐饮-品牌"),
    ("四季民福(呼家楼店)", "北京", "餐饮-具体门店"),
    ("北京华尔道夫酒店", "北京", "住宿-具体"),
    ("北京", "北京", "城市-宽泛"),
    ("王府井大街", "北京", "景点"),
]


async def test_one(client, keywords: str, city: str, label: str) -> dict:
    """测试单次查询，返回结构化结果"""
    try:
        raw = await call_tool("maps_text_search", {"keywords": keywords, "city": city})
        import json
        data = json.loads(raw)
        pois = data.get("pois", [])
        if pois:
            poi = pois[0]
            photos = poi.get("photos", {})
            has_photo = bool(photos.get("url") if isinstance(photos, dict) else False)
            photo_url = photos.get("url") if isinstance(photos, dict) else None
            return {
                "label": label,
                "query": f"{keywords}@{city}",
                "poi_name": poi.get("name", "?"),
                "address": poi.get("address", "?"),
                "has_photo": has_photo,
                "photo_url": photo_url[:80] + "..." if photo_url else None,
                "error": None,
            }
        else:
            return {"label": label, "query": f"{keywords}@{city}", "poi_name": None, "has_photo": False, "photo_url": None, "error": "no POI result"}
    except Exception as e:
        return {"label": label, "query": f"{keywords}@{city}", "poi_name": None, "has_photo": False, "photo_url": None, "error": str(e)[:100]}


async def main():
    print("🔧 检查配置...")
    print(f"   AMAP_MAPS_API_KEY 已配置: {bool(settings.amap_maps_api_key)}")
    print(f"   AMAP_MCP_SERVER_PATH: {repr(settings.amap_mcp_server_path)}")

    if not settings.amap_maps_api_key:
        print("\n❌ AMAP_MAPS_API_KEY 未配置，退出")
        return

    # 启动 MCP server
    print("\n🚀 启动 Amap MCP server...")
    try:
        proc = await _ensure_mcp_process()
        print(f"   ✅ 进程已启动 (PID {proc.pid})")
    except Exception as e:
        print(f"   ❌ 启动失败: {e}")
        return

    await asyncio.sleep(2)

    # 逐条测试
    print("\n📊 测试 Amap MCP 图片查询能力（按类型分组）")
    print("="*80)

    results = []
    for keywords, city, label in TEST_QUERIES:
        print(f"\n▶️  [{label}] {keywords} @ {city}")
        result = await test_one(None, keywords, city, label)
        results.append(result)

        if result["error"]:
            print(f"   ❌ 错误: {result['error']}")
        elif result["poi_name"]:
            print(f"   ✅ POI: {result['poi_name']}")
            print(f"   📍 地址: {result['address']}")
            if result["has_photo"]:
                print(f"   🖼  有图片: {result['photo_url']}")
            else:
                print(f"   ⚠️  无图片")
        else:
            print(f"   ⚠️  无结果")

    # 汇总
    print("\n" + "="*80)
    print("📊 汇总")
    print("="*80)

    total = len(results)
    with_photo = sum(1 for r in results if r["has_photo"])
    with_poi = sum(1 for r in results if r["poi_name"])
    errors = sum(1 for r in results if r["error"])

    print(f"\n总查询数: {total}")
    print(f"有 POI 结果: {with_poi}/{total}")
    print(f"有图片: {with_photo}/{total}")
    print(f"错误: {errors}/{total}")

    print("\n按类别命中率:")
    from collections import defaultdict
    cat_stats = defaultdict(lambda: {"total": 0, "has_photo": 0, "has_poi": 0})
    for r in results:
        # 提取类别（取 label 中 '-' 前部分）
        cat = r["label"].split("-")[0]
        cat_stats[cat]["total"] += 1
        if r["has_photo"]:
            cat_stats[cat]["has_photo"] += 1
        if r["poi_name"]:
            cat_stats[cat]["has_poi"] += 1

    for cat, stats in sorted(cat_stats.items()):
        total = stats["total"]
        print(f"  {cat}: {stats['has_photo']}/{total} 有图, {stats['has_poi']}/{total} 有 POI")

    print("\n详细结果列表:")
    print(f"{'类别':<15} {'查询':<25} {'POI名称':<20} {'有图':<5} {'照片URL'}")
    print("-" * 100)
    for r in results:
        poi = r["poi_name"][:18] if r["poi_name"] else "?"
        photo = "✅" if r["has_photo"] else "❌"
        url = r["photo_url"] if r["photo_url"] else "-"
        print(f"{r['label']:<15} {r['query']:<25} {poi:<20} {photo:<5} {url}")

    # 清理
    try:
        await close_mcp_process()
        print("\n🧹 MCP server 已关闭")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
