#!/usr/bin/env python3 -u
"""测试高德地理编码对失败地点的返回"""
import asyncio, httpx, json, os, sys
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings

GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

FAILED_SPOTS = [
    ("北京", "全聚德(北京和平门店)"),
    ("北京", "颐和园"),
    ("北京", "什刹海-胡同漫步"),
    ("北京", "南锣鼓巷"),
    ("北京", "上海返程"),
]

async def test_geocode():
    api_key = settings.amap_maps_api_key
    print(f"AMAP_MAPS_API_KEY: {'✅' if api_key else '❌'}")
    
    for city, name in FAILED_SPOTS:
        params = {"key": api_key, "address": name, "city": city, "output": "JSON"}
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(GEOCODE_URL, params=params)
            data = resp.json()
            status = data.get("status")
            count = data.get("count", "?")
            geocodes = data.get("geocodes", [])
            if geocodes:
                loc = geocodes[0].get("location", "?")
                addr = geocodes[0].get("formatted_address", "?")
                print(f"  ✅ {name}: status={status}, location={loc}, addr={addr[:50]}")
            else:
                print(f"  ❌ {name}: status={status}, count={count}, geocodes empty")
                if status != "1":
                    print(f"     info: {data.get('info', 'N/A')}")

if __name__ == "__main__":
    import sys
    asyncio.run(test_geocode())
