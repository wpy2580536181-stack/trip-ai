#!/usr/bin/env python3
"""
慢速测试 Amap MCP（模拟真实行程推荐间隔）

模拟真实行程推荐的调用节奏（每查询间隔 150ms），验证无限流情况下的命中率

用法：
  cd trip-backend && .venv/bin/python test_amap_slow.py
"""

import asyncio
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings
from src.services.mcp.amap_client import _ensure_mcp_process, call_tool, close_mcp_process


# 真实行程关键词
TEST_QUERIES = [
    ("故宫博物院", "北京"),
    ("天安门广场", "北京"),
    ("景山公园", "北京"),
    ("八达岭长城", "北京"),
    ("鸟巢", "北京"),
    ("全聚德(北京和平门店)", "北京"),
    ("四季民福烤鸭店(呼家楼店)", "北京"),
    ("护国寺小吃", "北京"),
    ("北京华尔道夫酒店", "北京"),
    ("wohkoon者行孙酒店(北京鸟巢北苑地铁站店)", "北京"),
    ("王府井大街", "北京"),
]


async def fetch_photo(city: str, name: str) -> dict:
    """查询单个 POI 图片，返回结构化结果"""
    try:
        raw = await call_tool("maps_text_search", {"keywords": name, "city": city})
        if not raw or not raw.strip():
            return {"name": name, "ok": False, "err": "empty response"}

        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"name": name, "ok": False, "err": f"invalid JSON: {raw[:50]}"}

        pois = data.get("pois", [])
        if not pois:
            return {"name": name, "ok": False, "err": "no POI"}

        poi = pois[0]
        photos = poi.get("photos", {})
        url = photos.get("url") if isinstance(photos, dict) else None

        return {"name": name, "ok": bool(url), "url": url, "poi_name": poi.get("name")}
    except Exception as exc:
        return {"name": name, "ok": False, "err": str(exc)[:80]}


async def main():
    print("🔧 检查配置...")
    print(f"   AMAP_MAPS_API_KEY 已配置: {bool(settings.amap_maps_api_key)}")
    if not settings.amap_maps_api_key:
        print("❌ 未配置 AMAP_MAPS_API_KEY")
        return

    # 启动 MCP
    try:
        await _ensure_mcp_process()
        await asyncio.sleep(2)
        print("✅ Amap MCP server 已启动")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return

    print(f"\n📊 慢速测试（间隔 150ms，模拟真实行程调用）")
    print("="*80)

    results = []
    t0 = asyncio.get_event_loop().time()

    for i, (name, city) in enumerate(TEST_QUERIES):
        print(f"[{i+1:2d}/{len(TEST_QUERIES)}] 查询: {name}...", end=" ", flush=True)

        r = await fetch_photo(city, name)
        results.append(r)

        if r["ok"]:
            poi_name = r.get("poi_name", name)
            print(f"✅ {poi_name}")
        else:
            err = r.get("err", "unknown")
            print(f"❌ {err}")

        # 间隔 150ms（模拟真实行程逐个查询）
        if i < len(TEST_QUERIES) - 1:
            await asyncio.sleep(0.15)

    t1 = asyncio.get_event_loop().time()
    total_time = t1 - t0

    # 汇总
    total = len(results)
    ok_count = sum(1 for r in results if r["ok"])
    print(f"\n{'='*80}")
    print(f"📊 总计: {ok_count}/{total} 有图 ({ok_count/total*100:.1f}%)")
    print(f"⏱  总耗时: {total_time:.1f}s（含 {0.15*(total-1):.1f}s 间隔）")
    print(f"{'='*80}")

    # 按类型分组
    from collections import defaultdict
    cats = defaultdict(lambda: {"total": 0, "ok": 0})
    for r in results:
        name = r["name"]
        if any(x in name for x in ["故宫", "天安门", "景山", "长城", "鸟巢", "广场"]):
            cat = "景点"
        elif any(x in name for x in ["全聚德", "四季民福", "护国寺"]):
            cat = "餐饮"
        elif any(x in name for x in ["酒店"]):
            cat = "住宿"
        else:
            cat = "其他"
        cats[cat]["total"] += 1
        if r["ok"]:
            cats[cat]["ok"] += 1

    print("\n按类型:")
    for cat, s in sorted(cats.items()):
        pct = s["ok"] / s["total"] * 100 if s["total"] else 0
        print(f"  {cat}: {s['ok']}/{s['total']} ({pct:.0f}%)")

    # 清理
    try:
        await close_mcp_process()
        print("\n🧹 MCP server 已关闭")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
