#!/usr/bin/env python3
"""
测试 Amap MCP 清理名称重试策略的效果

用法：
  cd trip-backend && .venv/bin/python test_amap_retry.py
"""

import asyncio
import sys
import os

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings
from src.services.mcp.amap_client import _ensure_mcp_process, call_tool, close_mcp_process
from src.services.unsplash_service import _fetch_amap_photo


# 测试用例：(原始名称, 城市)
TEST_CASES = [
    ("故宫博物院", "北京"),
    ("天安门广场", "北京"),
    ("全聚德(北京和平门店)", "北京"),
    ("四季民福烤鸭店(呼家楼店)", "北京"),
    ("北京华尔道夫酒店", "北京"),
    ("北京站", "北京"),
    ("鸟巢", "北京"),
    ("景山公园", "北京"),
]


async def test_one(name: str, city: str):
    """测试单次查询"""
    try:
        url = await _fetch_amap_photo(city, name)
        return {"name": name, "url": url}
    except Exception as e:
        return {"name": name, "url": None, "error": str(e)}


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
        print("✅ Amap MCP server 已启动\n")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return

    print("📊 测试 _fetch_amap_photo 重试策略（清理括号后重试）")
    print("="*80)

    results = []
    for name, city in TEST_CASES:
        r = await test_one(name, city)
        results.append(r)

        if r.get("error"):
            print(f"❌ {name}: 错误 {r['error']}")
        elif r.get("url"):
            print(f"✅ {name}: {r['url'][:60]}...")
        else:
            print(f"⚠️  {name}: 无图片（MCP 返回无图或 JSON 解析失败）")

    # 汇总
    total = len(results)
    has_url = sum(1 for r in results if r.get("url"))
    print(f"\n{'='*80}")
    print(f"总计: {has_url}/{total} 有图")
    print(f"{'='*80}")

    # 清理
    try:
        await close_mcp_process()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
