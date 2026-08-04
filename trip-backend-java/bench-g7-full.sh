#!/bin/bash

# G7 性能验证脚本（完整版）
# 目标：验证 Java 版本性能指标对齐 Python 基线

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
DURATION="${DURATION:-10}"
CONCURRENCY="${CONCURRENCY:-10}"

echo "=========================================="
echo "G7 性能验证（完整版）"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo "Duration: ${DURATION}s"
echo "Concurrency: $CONCURRENCY"
echo ""

# 1. 服务健康检查
echo "【1】服务健康检查"
HEALTH=$(curl -s "$BASE_URL/actuator/health" 2>&1)
if echo "$HEALTH" | grep -q "UP"; then
    echo "✅ 服务健康"
    echo "$HEALTH" | head -5
else
    echo "❌ 服务不可用"
    exit 1
fi
echo ""

# 2. 登录接口测试（QPS 基准）
echo "【2】登录接口 QPS 测试（受 rate limit 保护）"
python3 << 'PYEOF'
import asyncio
import time
import httpx
import sys

BASE_URL = "http://localhost:8000"
DURATION = 10
CONCURRENCY = 10

async def test_login():
    results = []
    start = time.monotonic()
    tasks = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        async def _request():
            req_start = time.monotonic()
            try:
                resp = await client.post("/api/user/login", json={"username": "e4test", "password": "EvalTest@2026"})
                elapsed = (time.monotonic() - req_start) * 1000
                results.append({"status": resp.status_code, "elapsed_ms": elapsed, "success": resp.is_success})
            except Exception as e:
                elapsed = (time.monotonic() - req_start) * 1000
                results.append({"status": 0, "elapsed_ms": elapsed, "success": False, "error": str(e)})

        while time.monotonic() - start < DURATION:
            tasks.append(_request())
            if len(tasks) >= CONCURRENCY:
                await asyncio.gather(*tasks)
                tasks = []

        if tasks:
            await asyncio.gather(*tasks)

    total = len(results)
    success = sum(1 for r in results if r.get("status") == 200)
    errors_429 = sum(1 for r in results if r.get("status") == 429)
    latencies = [r["elapsed_ms"] for r in results if r.get("status") == 200]

    if latencies:
        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.5)]
        p99_idx = int(len(sorted_lat) * 0.99)
        p99 = sorted_lat[min(p99_idx, len(sorted_lat)-1)]
    else:
        p50 = p99 = 0

    qps = total / DURATION
    effective_qps = success / DURATION if success else 0

    print(f"  总请求: {total}")
    print(f"  成功 (200): {success}")
    print(f"  限流 (429): {errors_429}")
    print(f"  总 QPS: {qps:.2f}")
    print(f"  有效 QPS: {effective_qps:.2f}")
    if success > 0:
        print(f"  P50 延迟: {p50:.2f}ms")
        print(f"  P99 延迟: {p99:.2f}ms")
    print(f"  备注: 登录接口受 rate limit 保护（20/min/user）")
    print(f"  Python 基线: 有效 QPS 0.27（受保护），历史接口 QPS 6.67")

try:
    asyncio.run(test_login())
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    sys.exit(1)
PYEOF

echo ""

# 3. 历史接口 QPS 测试（无 rate limit）
echo "【3】历史接口 QPS 测试（无 rate limit）"
python3 << 'PYEOF'
import asyncio
import time
import httpx
import sys

BASE_URL = "http://localhost:8000"
DURATION = 10
CONCURRENCY = 10
TOKEN = None

async def get_token():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post("/api/user/login", json={"username": "e4test", "password": "EvalTest@2026"})
        if resp.is_success:
            return resp.json().get("data", {}).get("token")
    return None

async def test_history():
    global TOKEN
    TOKEN = await get_token()
    if not TOKEN:
        print("  ❌ 无法获取 token")
        sys.exit(1)

    results = []
    start = time.monotonic()
    tasks = []

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        async def _request():
            req_start = time.monotonic()
            try:
                resp = await client.get("/api/history/trips", headers={"Authorization": f"Bearer {TOKEN}"})
                elapsed = (time.monotonic() - req_start) * 1000
                results.append({"status": resp.status_code, "elapsed_ms": elapsed, "success": resp.is_success})
            except Exception as e:
                elapsed = (time.monotonic() - req_start) * 1000
                results.append({"status": 0, "elapsed_ms": elapsed, "success": False, "error": str(e)})

        while time.monotonic() - start < DURATION:
            tasks.append(_request())
            if len(tasks) >= CONCURRENCY:
                await asyncio.gather(*tasks)
                tasks = []

        if tasks:
            await asyncio.gather(*tasks)

    total = len(results)
    success = sum(1 for r in results if r.get("status") == 200)
    errors_429 = sum(1 for r in results if r.get("status") == 429)
    latencies = [r["elapsed_ms"] for r in results if r.get("status") == 200]

    if latencies:
        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.5)]
        p99_idx = int(len(sorted_lat) * 0.99)
        p99 = sorted_lat[min(p99_idx, len(sorted_lat)-1)]
    else:
        p50 = p99 = 0

    qps = total / DURATION
    effective_qps = success / DURATION if success else 0

    print(f"  总请求: {total}")
    print(f"  成功 (200): {success}")
    print(f"  限流 (429): {errors_429}")
    print(f"  总 QPS: {qps:.2f}")
    print(f"  有效 QPS: {effective_qps:.2f}")
    if success > 0:
        print(f"  P50 延迟: {p50:.2f}ms")
        print(f"  P99 延迟: {p99:.2f}ms")
    print(f"  Python 基线: QPS 6.67, P99 < 10ms")

try:
    asyncio.run(test_history())
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    sys.exit(1)
PYEOF

echo ""

# 4. SSE 流式性能测试
echo "【4】SSE 流式性能测试（单并发）"
python3 << 'PYEOF'
import asyncio
import time
import httpx
import sys
import json

BASE_URL = "http://localhost:8000"
TOKEN = None

async def get_token():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post("/api/user/login", json={"username": "e4test", "password": "EvalTest@2026"})
        if resp.is_success:
            return resp.json().get("data", {}).get("token")
    return None

async def test_sse():
    global TOKEN
    TOKEN = await get_token()
    if not TOKEN:
        print("  ❌ 无法获取 token")
        sys.exit(1)

    print(f"  正在测试 SSE 流式接口...")
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=300) as client:
            async with client.stream(
                "POST",
                "/api/trip/chat",
                json={"message": "上海 2 天行程", "userId": 1},
                headers={"Authorization": f"Bearer {TOKEN}", "Accept": "text/event-stream"}
            ) as resp:
                if resp.status_code != 200:
                    print(f"  ❌ SSE 连接失败: {resp.status_code}")
                    print(f"  响应: {await resp.aread()}")
                    return

                chunk_count = 0
                first_chunk_time = None
                last_chunk_time = None

                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_count += 1
                        now = time.monotonic()
                        if first_chunk_time is None:
                            first_chunk_time = now
                            print(f"  首个 chunk: {(now - start) * 1000:.0f}ms")
                        last_chunk_time = now

                elapsed = time.monotonic() - start
                stream_duration = (last_chunk_time - first_chunk_time) if first_chunk_time and last_chunk_time else 0

                print(f"  ✅ SSE 流测试完成")
                print(f"  总耗时: {elapsed:.2f}s")
                print(f"  Chunk 数: {chunk_count}")
                if stream_duration > 0:
                    print(f"  流持续时间: {stream_duration:.2f}s")
                    print(f"  Python 基线: 15-21s（单并发）")
                else:
                    print(f"  流持续时间: N/A（没有数据）")

    except Exception as e:
        elapsed = time.monotonic() - start
        print(f"  ❌ SSE 测试失败 ({elapsed:.1f}s): {e}")

try:
    asyncio.run(test_sse())
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    sys.exit(1)
PYEOF

echo ""

# 5. 服务信息
echo "【5】服务信息"
INFO=$(curl -s "$BASE_URL/actuator/info" 2>&1)
echo "$INFO" | head -10 || echo "  (info 端点不可用)"
echo ""

echo "=========================================="
echo "✅ G7 性能验证完成"
echo "=========================================="
