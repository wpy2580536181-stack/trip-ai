#!/usr/bin/env python3
"""
直接验证修复效果：不经过 HTTP，直接调用 TripService.recommend() 核心逻辑
"""

import asyncio
import sys
import os
import json

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings
from src.utils.logger import setup_logging
import logging

# 减少日志噪音
setup_logging("WARNING")
logging.getLogger("src").setLevel(logging.WARNING)


async def test_trip_service_recommend():
    """测试 TripService.recommend() 的去重和时段隔离修复。"""
    from src.services.trip_service import TripService

    print("🔧 测试 TripService.recommend() 修复效果...")
    service = TripService()

    # 模拟一个已经通过 Agent 生成的行程（包含问题数据）
    parsed_trip = {
        "city": "北京",
        "days": 3,
        "totalBudget": 5000,
        "dailyItinerary": [
            {
                "day": 1,
                "morning": {"spot": "天安门", "duration": "2h", "ticket": "免费", "transportation": "地铁", "description": "看升旗"},
                "afternoon": {"spot": "天安门", "duration": "2h", "ticket": "免费", "transportation": "地铁", "description": "逛广场"},
                "evening": {"spot": "全聚德", "duration": "1h", "ticket": "", "transportation": "", "description": "吃烤鸭"},
                "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "lunch": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "dinner": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "accommodation": {"spot": "北京饭店", "duration": "", "ticket": "", "transportation": "", "description": ""},
            },
            {
                "day": 2,
                "morning": {"spot": "故宫", "duration": "3h", "ticket": "60元", "transportation": "地铁", "description": "参观故宫"},
                "afternoon": {"spot": "故宫", "duration": "2h", "ticket": "", "transportation": "", "description": "继续参观"},
                "evening": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "lunch": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "dinner": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "accommodation": {"spot": "北京饭店", "duration": "", "ticket": "", "transportation": "", "description": ""},
            },
            {
                "day": 3,
                "morning": {"spot": "天安门", "duration": "2h", "ticket": "免费", "transportation": "地铁", "description": "再次参观"},
                "afternoon": {"spot": "颐和园", "duration": "3h", "ticket": "30元", "transportation": "地铁", "description": "逛颐和园"},
                "evening": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "lunch": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "dinner": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                "accommodation": {"spot": "北京饭店", "duration": "", "ticket": "", "transportation": "", "description": ""},
            },
        ],
        "budgetBreakdown": {"accommodation": 1500, "food": 1000, "transportation": 800, "tickets": 500, "other": 1200},
        "tips": ["带好身份证"],
        "warnings": [],
    }

    print("\n📥 原始行程（包含已知问题）：")
    print("-" * 60)
    for day in parsed_trip["dailyItinerary"]:
        print(f"第 {day['day']} 天：")
        print(f"  上午：{day['morning']['spot']}")
        print(f"  下午：{day['afternoon']['spot']}")
        print(f"  晚上：{day['evening']['spot']}")
        print(f"  住宿：{day['accommodation']['spot']}")

    # 执行修复
    TripService._validate_and_fix_trip_data(parsed_trip)

    print("\n📤 修复后行程：")
    print("-" * 60)
    for day in parsed_trip["dailyItinerary"]:
        print(f"第 {day['day']} 天：")
        print(f"  上午：{day['morning']['spot']}")
        print(f"  下午：{day['afternoon']['spot']}")
        print(f"  晚上：{day['evening']['spot']}")
        print(f"  住宿：{day['accommodation']['spot']}")

    # 验证结果
    print("\n✅ 验证结果：")
    print("-" * 60)

    errors = []

    # 1. 检查天安门是否只出现一次
    tiananmen_count = sum(
        1 for day in parsed_trip["dailyItinerary"]
        for period in ["morning", "afternoon", "evening"]
        if day.get(period, {}).get("spot") == "天安门"
    )
    if tiananmen_count == 1:
        print("✅ 天安门仅出现 1 次（跨天去重生效）")
    else:
        errors.append(f"天安门出现 {tiananmen_count} 次，应为 1")

    # 2. 检查故宫是否只出现一次
    gugong_count = sum(
        1 for day in parsed_trip["dailyItinerary"]
        for period in ["morning", "afternoon", "evening"]
        if day.get(period, {}).get("spot") == "故宫"
    )
    if gugong_count == 1:
        print("✅ 故宫仅出现 1 次（跨天去重生效）")
    else:
        errors.append(f"故宫出现 {gugong_count} 次，应为 1")

    # 3. 检查全聚德是否被清空
    quanjudede_spots = [
        f"第{day['day']}天{period}"
        for day in parsed_trip["dailyItinerary"]
        for period in ["morning", "afternoon", "evening"]
        if day.get(period, {}).get("spot") == "全聚德"
    ]
    if not quanjudede_spots:
        print("✅ 全聚德被清空（时段隔离生效）")
    else:
        errors.append(f"全聚德仍出现在: {quanjudede_spots}")

    # 4. 检查北京饭店是否保留
    beijing_hotel_found = any(
        day.get("accommodation", {}).get("spot") == "北京饭店"
        for day in parsed_trip["dailyItinerary"]
    )
    if beijing_hotel_found:
        print("✅ 北京饭店保留在 accommodation（酒店识别正确）")
    else:
        errors.append("北京饭店被错误清空")

    # 5. 检查 Day 1 evening 全聚德被清空
    day1_evening = parsed_trip["dailyItinerary"][0].get("evening", {}).get("spot", "")
    if day1_evening == "":
        print("✅ Day 1 evening 全聚德被清空")
    else:
        errors.append(f"Day 1 evening 仍有值: {day1_evening}")

    # 6. 检查 Day 2 afternoon 故宫被清空
    day2_afternoon = parsed_trip["dailyItinerary"][1].get("afternoon", {}).get("spot", "")
    if day2_afternoon == "":
        print("✅ Day 2 afternoon 故宫被清空（重复景点）")
    else:
        errors.append(f"Day 2 afternoon 仍有值: {day2_afternoon}")

    print("\n" + "=" * 60)
    if errors:
        print("❌ 发现以下问题：")
        for err in errors:
            print(f"   - {err}")
        return False
    else:
        print("✅ 所有检查通过！修复效果符合预期。")
        return True


async def test_review_pool_compliance():
    """测试 review 候选池合规检查。"""
    from src.services.agent.review import review
    from src.services.agent.schemas import ResearchBundle, SpotItem

    print("\n🔍 测试 review 候选池合规检查...")
    print("=" * 60)

    # 构造包含候选池违规的行程
    raw_json = json.dumps({
        "city": "北京",
        "days": 2,
        "totalBudget": 5000,
        "dailyItinerary": [
            {"day": 1, "morning": {"spot": "天安门"}, "afternoon": {"spot": "故宫"}, "evening": {"spot": ""}},
            {"day": 2, "morning": {"spot": "长城"}, "afternoon": {"spot": "圆明园"}, "evening": {"spot": ""}},
        ],
        "budgetBreakdown": {"accommodation": 1500, "food": 1000, "transportation": 800, "tickets": 500, "other": 1200},
        "tips": [],
        "warnings": [],
    })

    # 候选池不包含长城
    bundle = ResearchBundle(
        attractions="北京景点",
        food="北京美食",
        attraction_items=[
            SpotItem(name="天安门", category="attraction"),
            SpotItem(name="故宫", category="attraction"),
            SpotItem(name="圆明园", category="attraction"),
        ],
        food_items=[],
    )

    parsed_plan, result = await review(
        raw_output=raw_json,
        bundle=bundle,
        budget=5000,
        days=2,
    )

    if result.passed is False and "长城" in str(result.issues):
        print("✅ 候选池违规检查生效：长城不在候选池中，行程被打回")
        return True
    else:
        print(f"❌ 候选池检查未生效: passed={result.passed}, issues={result.issues}")
        return False


async def main():
    print("🚀 开始验证行程规划修复效果\n")

    # 测试 1：数据修复逻辑
    test1_pass = await test_trip_service_recommend()

    # 测试 2：审阅合规检查
    test2_pass = await test_review_pool_compliance()

    # 总结
    print("\n" + "=" * 60)
    print("📊 验证总结：")
    print(f"   TripService 修复逻辑：{'✅ 通过' if test1_pass else '❌ 失败'}")
    print(f"   review 候选池检查：  {'✅ 通过' if test2_pass else '❌ 失败'}")

    if test1_pass and test2_pass:
        print("\n✅ 所有验证通过！修复效果符合预期。")
        return True
    else:
        print("\n❌ 部分验证失败，请检查修复代码。")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
