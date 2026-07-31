#!/usr/bin/env python3
"""
测试脚本：验证 enrich_trip_with_images / fetch_images 是否正确回写 imageUrl

用法：
  cd trip-backend && python test_image_enrichment.py
"""

import asyncio
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.services.unsplash_service import fetch_images, enrich_trip_with_images
from src.config.settings import settings


# =========================================================
# 构造 dailyItinerary 格式的行程
# =========================================================
SAMPLE_DAILY_ITINERARY = {
    "city": "北京",
    "days": 2,
    "totalBudget": 3500,
    "dailyItinerary": [
        {
            "day": 1,
            "morning": {
                "spot": "故宫博物院",
                "duration": "3小时",
                "ticket": "¥60",
                "transportation": "地铁1号线",
                "description": "中国明清两代的皇家宫殿。",
                "latitude": 39.9163,
                "longitude": 116.3972,
            },
            "afternoon": {
                "spot": "景山公园",
                "duration": "1.5小时",
                "ticket": "¥2",
                "transportation": "步行",
                "description": "位于故宫北面，可登高俯瞰全景。",
                "latitude": 39.9255,
                "longitude": 116.3967,
            },
            "evening": {
                "spot": "王府井大街",
                "duration": "2小时",
                "ticket": "免费",
                "transportation": "公交",
                "description": "北京最著名的商业街。",
                "latitude": 39.9139,
                "longitude": 116.4103,
            },
            "breakfast": {"spot": "护国寺小吃", "description": "老北京传统早餐"},
            "lunch":     {"spot": "四季民福故宫店", "description": "正宗北京烤鸭"},
            "dinner":    {"spot": "全聚德前门店", "description": "百年老字号烤鸭店"},
            "accommodation": {
                "spot": "北京华尔道夫酒店",
                "duration": "约¥1500/晚",
                "description": "位于王府井，交通便利。",
                "latitude": 39.9123,
                "longitude": 116.4101,
            },
        },
        {
            "day": 2,
            "morning": {
                "spot": "八达岭长城",
                "duration": "4小时",
                "ticket": "¥40",
                "transportation": "旅游专线",
                "description": "世界新七大奇迹之一。",
                "latitude": 40.3594,
                "longitude": 116.0199,
            },
            "afternoon": {
                "spot": "明十三陵",
                "duration": "2小时",
                "ticket": "¥45",
                "transportation": "旅游专线",
                "description": "明朝十三位皇帝的陵墓群。",
            },
            "evening": {
                "spot": "鸟巢",
                "duration": "1.5小时",
                "ticket": "¥50",
                "transportation": "地铁8号线",
                "description": "2008年北京奥运会主体育场。",
                "latitude": 39.9929,
                "longitude": 116.3967,
            },
        },
    ],
    "budgetBreakdown": {
        "accommodation": 3000,
        "food": 2000,
        "transportation": 500,
        "tickets": 145,
        "other": 200,
    },
    "tips": ["故宫需提前预约"],
    "warnings": ["北京夏季炎热，注意防暑"],
}


# =========================================================
# 打印结果
# =========================================================
def print_result(title: str, result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"📸 {title}")
    print(f"{'='*60}")

    found = 0
    missing = 0

    for day in result.get("dailyItinerary", []):
        day_num = day.get("day", "?")
        print(f"\n📅 第 {day_num} 天")

        for period in ("morning", "afternoon", "evening", "breakfast", "lunch", "dinner", "accommodation"):
            slot = day.get(period)
            if slot and slot.get("spot"):
                name = slot["spot"]
                img_url = slot.get("imageUrl")
                if img_url:
                    print(f"  ✅ {period}: {name}")
                    # 打印图片 URL（截断到 70 字符）
                    short_url = img_url if len(img_url) <= 70 else img_url[:67] + "..."
                    print(f"     🖼  {short_url}")
                    found += 1
                else:
                    print(f"  ❌ {period}: {name}（无图片）")
                    missing += 1

    print(f"\n{'─'*60}")
    print(f"总计：{found} 个有图片，{missing} 个无图片")
    print(f"{'='*60}\n")


# =========================================================
# 主流程
# =========================================================
async def main():
    print("🔧 检查环境配置...")
    print(f"   UNSPLASH_ACCESS_KEY 已配置: {bool(settings.unsplash_access_key)}")
    print(f"   AMAP_MAPS_API_KEY 已配置: {bool(settings.amap_maps_api_key)}")

    # ── Mock：Amap MCP 尚未配置路径，直接跳过，让 _fetch_amap_photo 返回 None 触发降级 ──
    from unittest.mock import patch
    from src.services.unsplash_service import _fetch_amap_photo

    async def _mock_fetch_amap_photo(city: str, name: str):
        return None  # Amap MCP 不可用，强制降级到 Unsplash

    with patch("src.services.unsplash_service._fetch_amap_photo", _mock_fetch_amap_photo):
        # ── 测试 1：enrich_trip_with_images（dailyItinerary 格式）──
        print("\n\n" + "▼" * 60)
        print("测试 1：enrich_trip_with_images（dailyItinerary 格式）")
        print("        [Amap MCP Mock: 返回 None → 降级 Unsplash]")
        print("▼" * 60)

        data1 = dict(SAMPLE_DAILY_ITINERARY)  # 深拷贝
        t0 = asyncio.get_event_loop().time()
        await enrich_trip_with_images(data1)
        t1 = asyncio.get_event_loop().time()
        print(f"⏱  耗时 {t1 - t0:.1f}s")
        print_result("enrich_trip_with_images（dailyItinerary）", data1)

        # ── 测试 2：fetch_images（days/spots 格式）──
        print("\n" + "▼" * 60)
        print("测试 2：fetch_images（days[*].spots[*] 格式）")
        print("        [Amap MCP Mock: 返回 None → 降级 Unsplash]")
        print("▼" * 60)

        days_data = {"city": "北京", "days": []}
        for d in SAMPLE_DAILY_ITINERARY["dailyItinerary"]:
            spots = []
            for p in ("morning", "afternoon", "evening"):
                slot = d.get(p)
                if slot and slot.get("spot"):
                    spots.append({"name": slot["spot"], "spot": slot["spot"]})
            days_data["days"].append({"spots": spots})

        t0 = asyncio.get_event_loop().time()
        result2 = await fetch_images(days_data)
        t1 = asyncio.get_event_loop().time()
        print(f"⏱  耗时 {t1 - t0:.1f}s")

        found2 = 0
        missing2 = 0
        for day in result2.get("days", []):
            for s in day.get("spots", []):
                name = s.get("name") or s.get("spot", "?")
                if s.get("imageUrl"):
                    print(f"  ✅ {name}: {s['imageUrl'][:60]}...")
                    found2 += 1
                else:
                    print(f"  ❌ {name}（无图片）")
                    missing2 += 1
        print(f"\n  总计：{found2} 有图，{missing2} 无图")


if __name__ == "__main__":
    asyncio.run(main())
