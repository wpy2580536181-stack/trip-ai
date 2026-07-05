"""
高德 POI 抓取脚本（Python 版）。

从高德地图 v5/place/text 接口批量抓取国内热门旅游城市的 POI 数据。
抓取三类：景点、美食、住宿。
原始数据输出到 data/poi_raw/{城市}.json。

用法: uv run python scripts/fetch_gaode_poi.py
"""

import asyncio
import json
import os
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).parent.parent

# 从 .env 读取 API Key
API_KEY = ""
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("GAODE_API_KEY="):
            API_KEY = line.split("=", 1)[1].strip().strip("\"'")
            break

if not API_KEY:
    API_KEY = os.environ.get("GAODE_API_KEY", "")

if not API_KEY:
    print("[Error] GAODE_API_KEY not set in .env")
    exit(1)

# ─── 城市列表 ───────────────────────────────────────────────

CITIES: list[dict] = [
    {"name": "北京", "region": "110000"},
    {"name": "上海", "region": "310000"},
    {"name": "广州", "region": "440100"},
    {"name": "深圳", "region": "440300"},
    {"name": "杭州", "region": "330100"},
    {"name": "南京", "region": "320100"},
    {"name": "成都", "region": "510100"},
    {"name": "重庆", "region": "500000"},
    {"name": "西安", "region": "610100"},
    {"name": "苏州", "region": "320500"},
    {"name": "长沙", "region": "430100"},
    {"name": "昆明", "region": "530100"},
    {"name": "厦门", "region": "350200"},
    {"name": "青岛", "region": "370200"},
    {"name": "大连", "region": "210200"},
    {"name": "天津", "region": "120000"},
    {"name": "武汉", "region": "420100"},
    {"name": "郑州", "region": "410100"},
    {"name": "济南", "region": "370100"},
    {"name": "福州", "region": "350100"},
    {"name": "宁波", "region": "330200"},
    {"name": "哈尔滨", "region": "230100"},
    {"name": "石家庄", "region": "130100"},
    {"name": "合肥", "region": "340100"},
    {"name": "南昌", "region": "360100"},
    {"name": "兰州", "region": "620100"},
    {"name": "太原", "region": "140100"},
    {"name": "贵阳", "region": "520100"},
    {"name": "乌鲁木齐", "region": "650100"},
    {"name": "桂林", "region": "450300"},
]


# ─── 过滤规则 ───────────────────────────────────────────────

EXCLUDE_TYPES = {"地铁站", "公交站", "停车场", "服务区", "加油站", "收费站"}


def _type_excluded(poi_type: str) -> bool:
    return any(e in poi_type for e in EXCLUDE_TYPES)


def is_scenic_poi(poi: dict) -> bool:
    return not _type_excluded(poi.get("type", ""))


def is_food_poi(poi: dict) -> bool:
    return "餐饮服务" in poi.get("type", "") and "酒店" not in poi.get("type", "")


def is_hotel_poi(poi: dict) -> bool:
    t = poi.get("type", "")
    return "住宿服务" in t or "宾馆" in t or "酒店" in t


# ─── API 调用 ───────────────────────────────────────────────


async def search_poi(
    client: httpx.AsyncClient,
    keywords: str,
    region: str,
    page_size: int = 25,
) -> list[dict]:
    """调用高德 v5/place/text 搜索 POI"""
    params = {
        "key": API_KEY,
        "keywords": keywords,
        "region": region,
        "pageSize": str(page_size),
        "page": "1",
    }
    resp = await client.get(
        "https://restapi.amap.com/v5/place/text",
        params=params,
        timeout=15,
    )
    data = resp.json()
    if data.get("status") != "1" or data.get("infocode") != "10000":
        return []
    return data.get("pois", [])


def dedup_pois(pois: list[dict]) -> list[dict]:
    """按 name|id 去重"""
    seen: set[str] = set()
    result = []
    for p in pois:
        key = f"{p.get('name', '')}|{p.get('id', '')}"
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


# ─── 主流程 ─────────────────────────────────────────────────


async def main():
    print("=== 高德 POI 抓取脚本 ===")
    print(f"城市数: {len(CITIES)}")

    output_dir = PROJECT_ROOT / "data" / "poi_raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    results_by_city: dict[str, dict] = {}
    total_fetched = 0

    async with httpx.AsyncClient() as client:
        for city in CITIES:
            cname = city["name"]
            region = city["region"]
            print(f"\n>>> 抓取 {cname} ...")

            scenic: list[dict] = []
            food: list[dict] = []
            hotel: list[dict] = []

            # 景点：取前15条有效
            raw = await search_poi(client, "景点", region, 25)
            for p in raw:
                if is_scenic_poi(p):
                    scenic.append(p)
                    if len(scenic) >= 15:
                        break
            print(f"  景点: {len(scenic)}/25 有效")
            total_fetched += len(scenic)

            # 美食：取前10条有效
            raw = await search_poi(client, "美食 特色菜", region, 20)
            for p in raw:
                if is_food_poi(p):
                    food.append(p)
                    if len(food) >= 10:
                        break
            print(f"  美食: {len(food)}/20 有效")
            total_fetched += len(food)

            # 住宿：取前5条有效
            raw = await search_poi(client, "酒店 宾馆", region, 15)
            for p in raw:
                if is_hotel_poi(p):
                    hotel.append(p)
                    if len(hotel) >= 5:
                        break
            print(f"  住宿: {len(hotel)}/15 有效")
            total_fetched += len(hotel)

            results_by_city[cname] = {
                "city": cname,
                "scenic": dedup_pois(scenic),
                "food": dedup_pois(food),
                "hotel": dedup_pois(hotel),
                "summary": {
                    "scenic": len(scenic),
                    "food": len(food),
                    "hotel": len(hotel),
                },
            }

            await asyncio.sleep(0.3)

    # 写入原始数据
    for cname, data in results_by_city.items():
        filepath = output_dir / f"{cname}.json"
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total = data["summary"]["scenic"] + data["summary"]["food"] + data["summary"]["hotel"]
        print(f"  ✓ {cname}: {total} POI (景点{data['summary']['scenic']} 美食{data['summary']['food']} 住宿{data['summary']['hotel']})")

    print(f"\n=== 完成 === 总抓取 POI: {total_fetched}，输出 {len(results_by_city)} 个城市")


if __name__ == "__main__":
    asyncio.run(main())
