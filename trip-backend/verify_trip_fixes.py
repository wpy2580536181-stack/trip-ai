#!/usr/bin/env python3 -u
"""综合验证：修复后完整流程测试

验证三点：
1. geocode_service 覆盖全部 7 个时段（breakfast/lunch/dinner/accommodation 应有经纬度）
2. accommodation.spot 若为餐饮店名会被清空（数据校验）
3. 地图上所有时段都有坐标（day 地图不消失）
"""
import asyncio, httpx, json, sys, os
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)
from src.config.settings import settings
from src.utils.logger import setup_logging

# 启用 DEBUG 日志
setup_logging("DEBUG")

BASE_URL = "http://localhost:8000/api"

async def main():
    print("🔧 检查后端...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/health", timeout=5)
            print(f"   ✅ 后端响应: {resp.text.strip()}")
        except Exception as e:
            print(f"   ❌ 后端未响应: {e}")
            return

        # 注册
        username = f"test_user_{__import__('uuid').uuid4().hex[:8]}"
        email = f"{username}@example.com"
        password = "TestPass123"
        print(f"\n🔑 注册测试用户: {username}...")
        resp = await client.post(f"{BASE_URL}/user/register", json={"username": username, "email": email, "password": password})
        if resp.status_code not in (200, 201):
            print(f"   ❌ 注册失败: {resp.status_code} {resp.text[:200]}")
            return
        token = resp.json()["data"]["token"]
        print(f"   ✅ token: {token[:20]}...")

        # 生成行程（3天，强制更多餐饮/住宿时段）
        print(f"\n📤 生成 3 天行程（北京）...")
        payload = {"city": "北京", "budget": 6000, "days": 3, "departureCity": "上海"}
        resp = await client.post(
            f"{BASE_URL}/trip/recommend",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(300.0),
        )
        print(f"   状态码: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   ❌ 失败: {resp.text[:500]}")
            return

        data = resp.json()
        if not data.get("success"):
            print(f"   ❌ 业务失败: {data.get('error')}")
            return

        trip = data.get("data", {})
        content = trip if "dailyItinerary" in trip else trip.get("content", {})
        daily = content.get("dailyItinerary", [])
        print(f"   ✅ 行程: {content.get('city')}, {content.get('days')}天, ¥{content.get('totalBudget')}")
        print(f"   📅 天数: {len(daily)}\n")

        # 统计
        total_spots = 0
        spots_with_coord = 0
        spots_without_coord = 0
        spots_with_img = 0
        accommodations = []
        acc_issues = []

        for i, day in enumerate(daily):
            day_num = day.get("day", i + 1)
            day_coords = 0
            day_no_coords = 0

            print(f"📅 第 {day_num} 天:")
            for period in ['morning', 'afternoon', 'evening', 'breakfast', 'lunch', 'dinner', 'accommodation']:
                slot = day.get(period)
                if slot and slot.get('spot'):
                    name = slot['spot']
                    has_lat = slot.get('latitude') is not None
                    has_lng = slot.get('longitude') is not None
                    has_img = 'imageUrl' in slot
                    total_spots += 1
                    if has_lat and has_lng:
                        spots_with_coord += 1
                        day_coords += 1
                        flag = "✅"
                    else:
                        spots_without_coord += 1
                        day_no_coords += 1
                        flag = "❌"
                    print(f"   {flag} {period}: {name} (coord={'✅' if has_lat and has_lng else '❌'}, img={'✅' if has_img else '❌'})")
                    if period == "accommodation":
                        accommodations.append(name)

            # 检查是否有整天地图可能消失
            if day_coords == 0:
                print(f"   ⚠️  该天所有时段均无经纬度，地图不会显示！")
            print()

        print(f"{'='*60}")
        print(f"📊 经纬度统计:")
        print(f"   有坐标: {spots_with_coord}/{total_spots} ({spots_with_coord/total_spots*100:.1f}%)")
        print(f"   无坐标: {spots_without_coord}/{total_spots}")
        print(f"{'='*60}\n")

        # 住宿校验
        print("🏨 住宿校验:")
        for idx, acc in enumerate(accommodations, 1):
            if not acc:
                print(f"   第{idx}天: (空) ✅ 正常")
            elif any(kw in acc for kw in ["酒店", "旅馆", "民宿", "hotel", "inn"]):
                print(f"   第{idx}天: {acc} ✅ 住宿类")
            else:
                print(f"   第{idx}天: {acc} ❌ 疑似非住宿类！")
                acc_issues.append(acc)
        print()

        # 保存数据供检查
        with open("/tmp/trip_verify_193.json", "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        print(f"💾 数据已保存 /tmp/trip_verify_193.json")

        # 总结
        print(f"\n{'='*60}")
        if spots_without_coord == 0:
            print("✅ 所有景点都有经纬度，地图全部显示")
        else:
            print(f"⚠️  {spots_without_coord} 个景点缺少经纬度")
        
        if not acc_issues:
            print("✅ accommodation 字段校验通过")
        else:
            print(f"❌ accommodation 有 {len(acc_issues)} 个异常: {acc_issues}")
        print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(main())
