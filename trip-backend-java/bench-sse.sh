#!/bin/bash

# Java 版 SSE 流式压测脚本
# 目标：验证 SSE 流 P99 在 15-21s 范围内（基线 47s）

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOTAL_STREAMS="${TOTAL_STREAMS:-20}"
CONCURRENCY_LEVELS="${CONCURRENCY_LEVELS:-1,5,10}"

echo "=========================================="
echo "Java SSE 性能测试"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo "Total Streams: $TOTAL_STREAMS"
echo "Concurrency Levels: $CONCURRENCY_LEVELS"
echo ""

# 检查服务
if ! curl -s -f "$BASE_URL/actuator/health" > /dev/null 2>&1; then
    echo "❌ 服务不可用: $BASE_URL"
    exit 1
fi

echo "✅ 服务可用"

# 创建临时结果目录
RESULTS_DIR="/tmp/java-sse-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS_DIR"

# 准备压测脚本
SCRIPT="$RESULTS_DIR/bench_sse.py"

cat > "$SCRIPT" << 'PYEOF'
import asyncio
import time
import sys
import json
import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
TOTAL_STREAMS = int(sys.argv[2]) if len(sys.argv) > 2 else 20
CONCURRENCY_LEVELS = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "1,5,10").split(",")]

TEST_MESSAGES = [
    "北京 2 天美食",
    "上海 1 天经典",
    "成都 3 天慢节奏",
    "西安 2 天文化",
]

async def run_sse_stream(client, message, headers):
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

async def run_concurrency(client, headers, concurrency, total):
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def _run(msg):
        async with sem:
            return await run_sse_stream(client, msg, headers)

    tasks = [_run(TEST_MESSAGES[i % len(TEST_MESSAGES)]) for i in range(total)]
    results = await asyncio.gather(*tasks)

    durations = [r["durationMs"] for r in results if "durationMs" in r and r["durationMs"] > 0]
    chunks = [r["chunks"] for r in results if "chunks" in r]
    errors = sum(1 for r in results if "error" in r and r["error"])

    metric = {
        "concurrency": concurrency,
        "totalStreams": total,
        "successStreams": total - errors,
        "durations": durations,
        "chunks": chunks,
        "errors": errors,
    }

    def percentile(arr, p):
        if not arr:
            return 0
        sorted_arr = sorted(arr)
        idx = int((len(sorted_arr) - 1) * p / 100)
        return sorted_arr[idx]

    p50 = percentile(durations, 50) / 1000 if durations else 0
    p99 = percentile(durations, 99) / 1000 if durations else 0

    print(f"  concurrency={concurrency}: success={total - errors}/{total}, "
          f"P50={p50:.1f}s, P99={p99:.1f}s")

    return metric

async def main():
    print(f"SSE Benchmark: {len(CONCURRENCY_LEVELS)} concurrency levels × {TOTAL_STREAMS} streams")
    print(f"Base URL: {BASE_URL}")

    # 获取 token
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            resp = await client.post("/api/user/login", json={"username": "e4test", "password": "EvalTest@2026"})
            if resp.is_success:
                token = resp.json().get("data", {}).get("token", "")
                headers = {"Authorization": f"Bearer {token}"}
            else:
                print(f"Warning: Login failed with status {resp.status_code}")
                headers = {}
    except Exception as e:
        print(f"Warning: Failed to get token: {e}")
        headers = {}

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as client:
        all_results = []
        for conc in CONCURRENCY_LEVELS:
            print(f"\nRunning concurrency={conc}...")
            metric = await run_concurrency(client, headers, conc, TOTAL_STREAMS)
            all_results.append(metric)

    result = {
        "scenario": "sse-java",
        "concurrencyLevels": CONCURRENCY_LEVELS,
        "results": all_results,
    }

    print("\n==========================================")
    print("SSE Results Summary:")
    for m in all_results:
        durations = m["durations"]
        if durations:
            def percentile(arr, p):
                sorted_arr = sorted(arr)
                idx = int((len(sorted_arr) - 1) * p / 100)
                return sorted_arr[idx]

            p50 = percentile(durations, 50) / 1000
            p99 = percentile(durations, 99) / 1000
            print(f"  conc={m['concurrency']}: P50={p50:.1f}s, P99={p99:.1f}s, "
                  f"success={m['successStreams']}/{m['totalStreams']}")
        else:
            print(f"  conc={m['concurrency']}: no successful streams")

    print("==========================================")
    print(json.dumps(result, indent=2))

asyncio.run(main())
PYEOF

echo "✅ SSE 压测脚本创建成功: $SCRIPT"

# 运行压测
echo ""
echo "开始 SSE 压测..."
python3 "$SCRIPT" "$BASE_URL" "$TOTAL_STREAMS" "$CONCURRENCY_LEVELS" 2>&1

# 清理
rm -rf "$RESULTS_DIR"

echo ""
echo "✅ SSE 压测完成"
