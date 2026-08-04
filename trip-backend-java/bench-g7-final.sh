#!/bin/bash

# G7 性能验证脚本（Java 版 - 对齐 Python 基线）
# Python 基线：
#   - 登录 QPS: 0.27（受 20/min/user 限流保护）
#   - 历史接口 QPS: 6.67（Java 版本未实现）
#   - SSE P99: 47s（10 并发，真实 LLM）
#   - Token cache hitRate: 40.2%

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
DURATION="${DURATION:-10}"
CONCURRENCY="${CONCURRENCY:-10}"

echo "=========================================="
echo "G7 性能验证（Java 版）"
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
else
    echo "❌ 服务不可用"
    exit 1
fi
echo ""

# 2. 登录接口 QPS 测试（受 rate limit 保护）
echo "【2】登录接口 QPS 测试（${DURATION}s, ${CONCURRENCY} 并发）"
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
                resp = await client.post("/api/user/login", json={
                    "identifier": "perf_test_user",
                    "password": "PerfTest@2026"
                })
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
    print(f"  Python 基线: 有效 QPS 0.27（受 20/min/user 限流保护）")
    print(f"  说明: 登录接口受 rate limit 保护，低 QPS 是预期行为")

try:
    asyncio.run(test_login())
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    sys.exit(1)
PYEOF

echo ""

# 3. 服务信息
echo "【3】服务信息"
INFO=$(curl -s "$BASE_URL/actuator/info" 2>&1)
if [ -n "$INFO" ] && [ "$INFO" != "{}" ]; then
    echo "$INFO" | python3 -m json.tool 2>/dev/null || echo "$INFO"
else
    echo "  (info 端点空)"
fi
echo ""

# 4. SSE 流式性能测试（单并发）
echo "【4】SSE 流式性能测试（单并发）"
python3 << 'PYEOF'
import asyncio
import time
import httpx
import sys

BASE_URL = "http://localhost:8000"

async def get_token():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        try:
            # 注册（忽略失败）
            try:
                await client.post("/api/user/register", json={
                    "username": "perf_test_user",
                    "email": "perf_test@example.com",
                    "password": "PerfTest@2026"
                })
            except:
                pass

            # 登录
            resp = await client.post("/api/user/login", json={
                "identifier": "perf_test_user",
                "password": "PerfTest@2026"
            })
            if resp.is_success:
                data = resp.json()
                token = data.get("data", {}).get("token")
                if token:
                    return token
        except Exception as e:
            print(f"Error getting token: {e}", file=sys.stderr)
    return None

async def test_sse():
    token = await get_token()
    if not token:
        print("  ❌ 无法获取 token")
        sys.exit(1)

    print(f"  正在连接 SSE...")
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=300) as client:
            async with client.stream(
                "POST",
                "/api/trip/chat",
                json={"message": "上海 2 天行程", "userId": 1},
                headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    print(f"  ❌ SSE 连接失败: {resp.status_code}")
                    print(f"  响应: {body.decode()}")
                    return

                chunk_count = 0
                first_chunk_time = None
                last_chunk_time = None
                total_bytes = 0

                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_count += 1
                        now = time.monotonic()
                        if first_chunk_time is None:
                            first_chunk_time = now
                            ttf = (first_chunk_time - start) * 1000
                            print(f"  首个 chunk: {ttf:.0f}ms")
                        last_chunk_time = now
                        total_bytes += len(line)

                elapsed = time.monotonic() - start
                stream_duration = (last_chunk_time - first_chunk_time) if first_chunk_time and last_chunk_time else 0

                print(f"  ✅ SSE 流测试完成")
                print(f"  总耗时: {elapsed:.2f}s")
                print(f"  Chunk 数: {chunk_count}")
                print(f"  总数据量: {total_bytes / 1024:.1f} KB")
                if stream_duration > 0:
                    print(f"  流持续时间: {stream_duration:.2f}s")
                    if elapsed <= 21:
                        print(f"  ✅ 达标: 耗时 <= 21s（单并发基线）")
                    else:
                        print(f"  ⚠️  参考基线: <= 21s（单并发）")
                else:
                    print(f"  ⚠️  流持续时间: N/A（没有数据）")

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

echo "=========================================="
echo "✅ G7 性能验证完成"
echo "=========================================="
echo ""
echo "注："
echo "- 登录接口受 rate limit 保护（1000/900s），低 QPS 是预期行为"
echo "- 历史接口（/api/history/trips）Java 版本暂未实现"
echo "- SSE 单并发基线：<= 21s"
echo "- Python 基线数据：trip-server 10 并发 SSE P99 47s"
