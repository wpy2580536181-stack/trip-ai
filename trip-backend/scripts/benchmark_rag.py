"""
RAG 检索速度压测（Python 版）。

用法: uv run python scripts/benchmark_rag.py
"""

import asyncio
import time
import sys
from pathlib import Path

# 确保 src 可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.knowledge_service import KnowledgeService

# 15 条测试 query（覆盖热门景点、长尾查询、模糊语义）
QUERIES: list[dict] = [
    {"query": "北京故宫博物院的开放时间", "city": "北京", "category": "景点"},
    {"query": "上海外滩附近有什么好玩的", "city": "上海", "category": "景点"},
    {"query": "成都最适合晚上去的景点", "city": "成都", "category": "景点"},
    {"query": "西安兵马俑门票多少钱", "city": "西安", "category": "景点"},
    {"query": "杭州西湖边上的餐厅推荐", "city": "杭州", "category": "美食"},
    {"query": "桂林阳朔西街住宿", "city": "桂林", "category": "住宿"},
    {"query": "丽江古城到玉龙雪山怎么走", "city": "丽江", "category": "景点"},
    {"query": "拉萨适合高反人群的景点", "city": "拉萨", "category": "景点"},
    {"query": "三亚海鲜便宜的地方", "city": "三亚", "category": "美食"},
    {"query": "张家界国家森林公园游玩路线", "city": "张家界", "category": "景点"},
    {"query": "带老人小孩去哪个城市方便", "city": "成都", "category": "景点"},
    {"query": "夏天避暑去哪里比较好", "city": "重庆", "category": "景点"},
    {"query": "适合情侣约会的浪漫餐厅", "city": "上海", "category": "美食"},
    {"query": "预算200以内住哪里", "city": "北京", "category": "住宿"},
    {"query": "看夜景最好的地方", "city": "广州", "category": "景点"},
]


async def main():
    print("=== RAG 检索速度压测 ===\n")
    print(f"查询数: {len(QUERIES)}\n")

    # 预热
    print("预热中...")
    await KnowledgeService.search_spots("北京", city="北京", category="景点", limit=5)
    print("预热完成\n")

    times: list[float] = []

    for i, q in enumerate(QUERIES):
        start = time.perf_counter()
        try:
            result = await KnowledgeService.search_spots(
                q["query"],
                city=q["city"],
                category=q["category"],
                limit=5,
            )
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            item_count = str(result).count("---") + 1 if result else 0
            print(f"  [{i + 1:>2}] {elapsed:>6.0f}ms | {item_count} 项 | {q['query'][:20]}")
        except Exception as e:
            print(f"  [{i + 1:>2}]   FAIL | {q['query'][:20]} | {e}")

    if not times:
        print("\n❌ 所有查询均失败")
        return

    # 统计
    sorted_times = sorted(times)
    avg = sum(times) / len(times)
    p50 = sorted_times[int(len(sorted_times) * 0.5)]
    p95 = sorted_times[int(len(sorted_times) * 0.95)]
    p99 = sorted_times[int(len(sorted_times) * 0.99)]

    print("\n=== 结果 ===")
    print(f"  平均: {avg:>6.0f}ms")
    print(f"  最小: {sorted_times[0]:>6.0f}ms")
    print(f"  最大: {sorted_times[-1]:>6.0f}ms")
    print(f"  P50:  {p50:>6.0f}ms")
    print(f"  P95:  {p95:>6.0f}ms")
    print(f"  P99:  {p99:>6.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
