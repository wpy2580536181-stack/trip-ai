#!/bin/bash

# Java 版 HTTP 压测脚本（登录 + 历史记录）
# 目标：验证 QPS ≥ 6.0（基线 6.67）

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
DURATION="${DURATION:-30}"
CONCURRENCY="${CONCURRENCY:-10}"

echo "=========================================="
echo "Java HTTP 性能测试"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo "Duration: ${DURATION}s"
echo "Concurrency: $CONCURRENCY"
echo ""

# 检查服务可用性
if ! curl -s -f "$BASE_URL/actuator/health" > /dev/null 2>&1; then
    echo "❌ 服务不可用: $BASE_URL"
    exit 1
fi

echo "✅ 服务可用"

# 创建临时结果文件
RESULTS_DIR="/tmp/java-bench-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS_DIR"

# 准备压测脚本（Python 脚本依赖 httpx，使用系统 Python）
SCRIPT="$RESULTS_DIR/bench_http.py"

cat > "$SCRIPT" << 'PYEOF'
import asyncio
import time
import sys
import json
import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 30
CONCURRENCY = int(sys.argv[3]) if len(sys.argv) > 3 else 10

LOGIN_BODY = {"username": "e4test", "password": "EvalTest@2026"}

async def bench_endpoint(client, method, url, body=None, headers=None):
    results = []
    start_time = time.monotonic()
    tasks = []

    async def _request():
        nonlocal results
        req_start = time.monotonic()
        try:
            if method == "POST":
                resp = await client.post(url, json=body, headers=headers)
            else:
                resp = await client.get(url, headers=headers)
            elapsed = (time.monotonic() - req_start) * 1000
            results.append({
                "status": resp.status_code,
                "elapsed_ms": elapsed,
                "success": resp.is_success,
            })
        except Exception as e:
            elapsed = (time.monotonic() - req_start) * 1000
            results.append({"status": 0, "elapsed_ms": elapsed, "success": False, "error": str(e)})

    while time.monotonic() - start_time < DURATION:
        tasks.append(_request())
        if len(tasks) >= CONCURRENCY:
            await asyncio.gather(*tasks)
            tasks = []

    if tasks:
        await asyncio.gather(*tasks)

    return results

def stats(results, label):
    total = len(results)
    success = sum(1 for r in results if r.get("status") == 200)
    errors = sum(1 for r in results if r.get("status") == 0)
    non2xx = sum(1 for r in results if r.get("status") != 0 and r.get("status") != 200)
    latencies = [r["elapsed_ms"] for r in results if r.get("status") == 200]
    all_latencies = [r["elapsed_ms"] for r in results]

    qps = total / DURATION
    effective_qps = success / DURATION if success else 0

    sorted_lat = sorted(latencies) if latencies else [0]

    def pct(p):
        if not sorted_lat:
            return 0
        idx = int((len(sorted_lat) - 1) * p / 100)
        return round(sorted_lat[idx], 2)

    result = {
        "label": label,
        "qps": round(qps, 2),
        "effectiveQps": round(effective_qps, 3),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "max": round(max(all_latencies), 2) if all_latencies else 0,
        "totalRequests": total,
        "success2xx": success,
        "errors": errors,
        "non2xx": non2xx,
        "successRate": round(success / total, 6) if total else 0,
    }
    return result

async def main():
    print(f"HTTP Benchmark: {CONCURRENCY} connections × {DURATION}s")
    print(f"Base URL: {BASE_URL}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # 登录压测
        print("\nBenchmarking POST /api/user/login ...")
        login_results = await bench_endpoint(
            client, "POST", "/api/user/login", body=LOGIN_BODY
        )
        login_stats = stats(login_results, "login")

        # 历史记录压测（需要先获取 token）
        print("\nBenchmarking GET /api/history/trips ...")
        try:
            resp = await client.post("/api/user/login", json=LOGIN_BODY, timeout=10)
            if resp.is_success:
                token = resp.json().get("data", {}).get("token")
                headers = {"Authorization": f"Bearer {token}"}
            else:
                headers = {}
        except:
            headers = {}

        history_results = await bench_endpoint(
            client, "GET", "/api/history/trips", headers=headers
        )
        history_stats = stats(history_results, "history")

    # 输出结果
    print("\n==========================================")
    print("Results:")
    print(f"Login:      QPS={login_stats['effectiveQps']}, P99={login_stats['p99']}ms")
    print(f"History:    QPS={history_stats['effectiveQps']}, P99={history_stats['p99']}ms")
    print("==========================================")

    # 保存结果
    result = {
        "scenario": "http-java",
        "login": login_stats,
        "history": history_stats,
    }
    print(json.dumps(result, indent=2))

asyncio.run(main())
PYEOF

echo "✅ 压测脚本创建成功: $SCRIPT"

# 运行压测
echo ""
echo "开始压测..."
python3 "$SCRIPT" "$BASE_URL" "$DURATION" "$CONCURRENCY" 2>&1

# 清理
rm -rf "$RESULTS_DIR"

echo ""
echo "✅ 压测完成"
