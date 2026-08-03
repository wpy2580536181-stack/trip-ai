#!/bin/bash

# G7 性能验证脚本（简化版）
# 目标：验证 Java 版本基本性能指标

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=========================================="
echo "G7 性能验证（简化版）"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

# 1. 服务健康检查
echo "【1】服务健康检查"
HEALTH=$(curl -s "$BASE_URL/actuator/health" 2>&1)
if echo "$HEALTH" | grep -q "UP"; then
    echo "✅ 服务健康"
else
    echo "❌ 服务不可用"
    exit 1
fi
echo ""

# 2. 登录接口测试（10 并发 × 10s）
echo "【2】登录接口 QPS 测试"
python3 << 'PYEOF'
import asyncio
import time
import httpx

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

asyncio.run(test_login())
PYEOF

echo ""

# 3. 服务信息
echo "【3】服务信息"
curl -s "$BASE_URL/actuator/info" 2>&1 | head -10 || echo "  (info 端点不可用)"
echo ""

echo "=========================================="
echo "✅ G7 性能验证完成"
echo "=========================================="
