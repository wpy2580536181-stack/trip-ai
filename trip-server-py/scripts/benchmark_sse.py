"""SSE 流式压测脚本（对应 Node 版 benchmark-sse.ts）

测试端点：POST /api/trip/chat
测试 4 个并发级别：1, 5, 10, 20
每个级别发送 20 个 SSE 流请求，统计耗时、chunk 数、token 用量。
"""

import asyncio
import json
import os
import time

import httpx

from benchmark_lib.auth import get_auth_header, BASE_URL
from benchmark_lib.store import get_env, percentile, save_result

TOTAL_STREAMS = int(os.getenv("SSE_TOTAL_STREAMS", "20"))
CONCURRENCY_LEVELS = [int(x) for x in os.getenv("SSE_CONCURRENCY_LEVELS", "1,5,10,20").split(",")]

# 8 条测试消息（与 Node 版一致）
TEST_MESSAGES = [
    "北京 2 天美食",
    "上海 1 天经典",
    "成都 3 天慢节奏",
    "西安 2 天文化",
    "杭州 1 天西湖",
    "广州 2 天美食",
    "深圳 1 天现代",
    "重庆 2 天夜景",
]


async def run_sse_stream(client: httpx.AsyncClient, message: str,
                         headers: dict) -> dict:
    """运行单个 SSE 流请求"""
    start = time.monotonic()
    chunks = 0
    tokens = {}

    try:
        async with client.stream(
            "POST", "/api/trip/chat",
            json={"message": message},
            headers=headers,
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "durationMs": 0}

            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        ev_type = data.get("type")
                        if ev_type == "chunk":
                            chunks += 1
                        elif ev_type == "complete":
                            usage = data.get("data", {}).get("usage", {})
                            tokens = {
                                "prompt": usage.get("prompt", 0),
                                "completion": usage.get("completion", 0),
                                "total": usage.get("total", 0),
                            }
                    except json.JSONDecodeError:
                        pass

            duration = (time.monotonic() - start) * 1000
            return {"durationMs": duration, "chunks": chunks, "tokens": tokens}

    except Exception as e:
        return {"error": str(e), "durationMs": (time.monotonic() - start) * 1000}


async def run_concurrency(client: httpx.AsyncClient, headers: dict,
                          concurrency: int, total: int) -> dict:
    """以指定并发级别运行 SSE 测试"""
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def _run(msg: str):
        async with sem:
            return await run_sse_stream(client, msg, headers)

    tasks = [_run(TEST_MESSAGES[i % len(TEST_MESSAGES)]) for i in range(total)]
    results = await asyncio.gather(*tasks)

    durations = [r["durationMs"] for r in results if "durationMs" in r and r["durationMs"] > 0]
    chunks = [r["chunks"] for r in results if "chunks" in r]
    token_counts = [r["tokens"] for r in results if "tokens" in r and r["tokens"]]
    errors = sum(1 for r in results if "error" in r and r["error"])

    metric = {
        "concurrency": concurrency,
        "totalStreams": total,
        "successStreams": total - errors,
        "streamDurationsMs": durations,
        "chunkCounts": chunks,
        "tokenCounts": token_counts,
        "errors": errors,
    }

    p50 = percentile(durations, 50) / 1000 if durations else 0
    p99 = percentile(durations, 99) / 1000 if durations else 0
    print(f"  concurrency={concurrency}: success={total - errors}/{total}, "
          f"P50={p50:.1f}s, P99={p99:.1f}s")

    return metric


async def main():
    print(f"SSE Benchmark: {len(CONCURRENCY_LEVELS)} concurrency levels × {TOTAL_STREAMS} streams")
    print(f"Base URL: {BASE_URL}")

    print("Getting auth token...")
    headers = get_auth_header(BASE_URL)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as client:
        all_results = []
        for conc in CONCURRENCY_LEVELS:
            print(f"Running concurrency={conc}...")
            metric = await run_concurrency(client, headers, conc, TOTAL_STREAMS)
            all_results.append(metric)

    result = {
        "scenario": "sse",
        "env": get_env(),
        "results": all_results,
    }

    save_result("sse-results", result)
    print("SSE benchmark complete.")


if __name__ == "__main__":
    asyncio.run(main())
