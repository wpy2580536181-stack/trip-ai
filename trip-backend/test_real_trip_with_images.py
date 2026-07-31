#!/usr/bin/env python3
"""
端到端验证：调用真实后端推荐接口，验证图片是否附加到行程数据

需要后端已运行在 localhost:8000

用法：
  cd trip-backend && .venv/bin/python test_real_trip_with_images.py
"""

import asyncio
import os
import sys
import json
import uuid

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

import httpx
from src.config.settings import settings
from src.utils.logger import setup_logging
import logging

# 启用 DEBUG 日志
setup_logging("DEBUG")
print(f"🔍 Root logger level: {logging.getLogger().level} ({logging.getLevelName(logging.getLogger().level)})")
print(f"🔍 trip_log effective level: {logging.getLogger('trip').getEffectiveLevel()} ({logging.getLevelName(logging.getLogger('trip').getEffectiveLevel())})")


BASE_URL = "http://localhost:8000/api"


async def register_and_login(client: httpx.AsyncClient) -> str:
    """注册测试用户并返回 token。"""
    username = f"test_user_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "TestPass123"

    print(f"🔑 注册测试用户: {username}...")
    resp = await client.post(
        f"{BASE_URL}/user/register",
        json={"username": username, "email": email, "password": password},
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"注册失败 ({resp.status_code}): {resp.text[:200]}")

    token = resp.json()["data"]["token"]
    print(f"   ✅ 注册成功，获取 token: {token[:20]}...")

    return token


async def main():
    print("🔧 检查后端服务...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{BASE_URL}/health", timeout=5)
            print(f"   ✅ 后端响应: {resp.text.strip()}")
        except Exception as e:
            print(f"   ❌ 后端未响应: {e}")
            return

    # 获取 token
    async with httpx.AsyncClient() as client:
        try:
            token = await register_and_login(client)
        except Exception as e:
            print(f"   ❌ 注册/登录失败: {e}")
            return

    # 构造推荐请求
    payload = {
        "city": "北京",
        "budget": 5000,
        "days": 2,
        "departureCity": "上海",
    }

    print(f"\n📤 发送行程推荐请求: {json.dumps(payload, ensure_ascii=False)}")
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/trip/recommend",
                json=payload,
                headers=headers,
            )
            print(f"   状态码: {resp.status_code}")

            if resp.status_code != 200:
                print(f"   ❌ 请求失败: {resp.text[:500]}")
                return

            data = resp.json()
            if not data.get("success"):
                print(f"   ❌ 业务失败: {data.get('error', 'unknown')}")
                return

            trip_data = data.get("data", {})
            print(f"   ✅ 行程生成成功")
            print(f"   - 城市: {trip_data.get('city')}")
            print(f"   - 天数: {trip_data.get('days')}")
            print(f"   - 预算: ¥{trip_data.get('totalBudget')}")
            
            # 调试：保存完整响应到文件
            with open("/tmp/trip_response.json", "w", encoding="utf-8") as f:
                json.dump(trip_data, f, ensure_ascii=False, indent=2)
            print(f"\n💾 完整响应已保存到 /tmp/trip_response.json")

            # 检查每日行程的图片
            daily = trip_data.get("dailyItinerary", [])
            print(f"\n📸 检查每日景点图片:")

            total_spots = 0
            spots_with_image = 0

            for day in daily:
                day_num = day.get("day", "?")
                print(f"\n   📅 第 {day_num} 天:")

                for period in ("morning", "afternoon", "evening", "breakfast", "lunch", "dinner", "accommodation"):
                    slot = day.get(period)
                    if slot and slot.get("spot"):
                        name = slot["spot"]
                        total_spots += 1
                        img_url = slot.get("imageUrl")
                        if img_url:
                            print(f"     ✅ {period}: {name}")
                            print(f"        🖼  {img_url[:80]}...")
                            spots_with_image += 1
                        else:
                            print(f"     ❌ {period}: {name} (无图片)")

            print(f"\n{'='*60}")
            print(f"📊 总计: {spots_with_image}/{total_spots} 个景点有图片")
            print(f"{'='*60}\n")

            # 检查 budgetBreakdown
            budget = trip_data.get("budgetBreakdown", {})
            if budget:
                print("💰 预算明细:")
                print(f"   - 住宿: ¥{budget.get('accommodation', 0)}")
                print(f"   - 餐饮: ¥{budget.get('food', 0)}")
                print(f"   - 交通: ¥{budget.get('transportation', 0)}")
                print(f"   - 门票: ¥{budget.get('tickets', 0)}")
                print(f"   - 其他: ¥{budget.get('other', 0)}")
                print(f"   - 总计: ¥{trip_data.get('totalBudget', 0)}")

        except Exception as e:
            print(f"   ❌ 请求异常: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
