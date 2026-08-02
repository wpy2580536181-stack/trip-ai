#!/usr/bin/env python3
"""真实行程验证脚本：直接调用 TripService.recommend()，不经过 HTTP。"""

import asyncio
import sys
import os
import json
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings
from src.utils.logger import setup_logging
import logging

setup_logging("DEBUG")
logger = logging.getLogger(__name__)


async def main():
    from src.services.trip_service import TripService

    print("🔧 初始化 TripService...")
    service = TripService()

    # 测试请求
    test_cases = [
        {"city": "北京", "budget": 5000, "days": 3, "departure_city": "上海"},
    ]

    for case in test_cases:
        print(f"\n📤 测试用例：{case['city']} {case['days']}天游，预算{case['budget']}元")
        print("=" * 60)

        try:
            result = await service.recommend(
                user_id=0,  # 测试用户
                city=case["city"],
                budget=case["budget"],
                days=case["days"],
                departure_city=case["departure_city"],
            )

            if not result.get("success"):
                print(f"❌ 行程推荐失败: {result.get('error', 'unknown')}")
                continue

            parsed = result.get("data", {}).get("trip_data", {})
            if not parsed:
                print("❌ 未返回行程数据")
                continue

            # 打印行程概览
            itinerary = parsed.get("dailyItinerary", [])
            print(f"✅ 生成 {len(itinerary)} 天行程")
            print("\n📅 行程详情：")
            print("-" * 60)

            all_spots = []  # 收集所有景点用于去重检查

            for day in itinerary:
                day_num = day.get("day", "?")
                print(f"\n第 {day_num} 天：")

                # 上午
                morning = day.get("morning", {})
                if morning.get("spot"):
                    print(f"  ☀️ 上午：{morning['spot']}")
                    all_spots.append(morning['spot'])

                # 下午
                afternoon = day.get("afternoon", {})
                if afternoon.get("spot"):
                    print(f"  🌤️ 下午：{afternoon['spot']}")
                    all_spots.append(afternoon['spot'])

                # 晚上
                evening = day.get("evening", {})
                if evening.get("spot"):
                    print(f"  🌙 晚上：{evening['spot']}")
                    all_spots.append(evening['spot'])

                # 餐饮
                breakfast = day.get("breakfast", {})
                if breakfast.get("spot"):
                    print(f"  🍳 早餐：{breakfast['spot']}")

                lunch = day.get("lunch", {})
                if lunch.get("spot"):
                    print(f"  🍚 午餐：{lunch['spot']}")

                dinner = day.get("dinner", {})
                if dinner.get("spot"):
                    print(f"  🍽️ 晚餐：{dinner['spot']}")

                # 住宿
                accom = day.get("accommodation", {})
                if accom.get("spot"):
                    print(f"  🏨 住宿：{accom['spot']}")

            # 检查去重
            print("\n" + "=" * 60)
            print("🔍 去重检查：")
            seen = set()
            duplicates = []
            for idx, spot in enumerate(all_spots, 1):
                day_idx = (idx - 1) // 3 + 1
                period = ["上午", "下午", "晚上"][(idx - 1) % 3]
                if spot in seen:
                    duplicates.append(f"第{day_idx}天{period}：{spot}")
                seen.add(spot)

            if duplicates:
                print("❌ 发现重复景点：")
                for d in duplicates:
                    print(f"   - {d}")
            else:
                print("✅ 无重复景点")

            # 检查餐饮进入景点时段
            print("\n🔍 时段隔离检查：")
            food_keywords = ["烤鸭", "餐厅", "餐馆", "饭店", "火锅", "小吃", "面", "菜", "食", "茶", "咖啡", "bar", "cafe", "restaurant", "全聚德"]
            violations = []
            for day in itinerary:
                day_num = day.get("day", "?")
                for period in ["morning", "afternoon", "evening"]:
                    slot = day.get(period, {})
                    spot = slot.get("spot", "")
                    if spot and any(kw.lower() in spot.lower() for kw in food_keywords):
                        violations.append(f"第{day_num}天 {period}：{spot}")

            if violations:
                print("❌ 发现餐饮进入景点时段：")
                for v in violations:
                    print(f"   - {v}")
            else:
                print("✅ 时段隔离正常")

            # 打印 budgetBreakdown
            budget = parsed.get("budgetBreakdown", {})
            print("\n💰 预算分解：")
            for k, v in budget.items():
                print(f"   {k}: {v}元")

        except Exception as e:
            print(f"❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
