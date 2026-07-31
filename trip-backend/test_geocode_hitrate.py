#!/usr/bin/env python3 -u
"""测试 geocode_service 对不同类型地点的命中率"""
import asyncio, sys, os
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.services.geocode_service import geocode_spot, _clean_spot_name, _GeocodeQueue

TEST_SPOTS = [
    ("北京", "天安门广场"),
    ("北京", "故宫博物院（午门）"),
    ("北京", "全聚德(北京和平门店)"),
    ("北京", "四季民福烤鸭店(呼家楼店)"),
    ("北京", "颐和园"),
    ("北京", "什刹海-胡同漫步"),
    ("北京", "南锣鼓巷"),
    ("北京", "上海返程"),
    ("北京", "酒店自助早餐"),
    ("北京", "附近快餐店"),
    ("北京", "南锣鼓巷小吃街"),
    ("北京", "wohkoon者行孙酒店(北京鸟巢北苑地铁站店)"),
]

async def main():
    print(f"测试 {len(TEST_SPOTS)} 个地点:\n")
    ok = 0
    fail = 0
    
    for city, name in TEST_SPOTS:
        print(f"  {name}...", end=" ", flush=True)
        result = await geocode_spot(name, city)
        if result:
            print(f"✅ lat={result['lat']:.4f}, lng={result['lng']:.4f}")
            ok += 1
        else:
            print(f"❌")
            fail += 1
    
    print(f"\n总计: {ok}/{len(TEST_SPOTS)} ({ok/len(TEST_SPOTS)*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
