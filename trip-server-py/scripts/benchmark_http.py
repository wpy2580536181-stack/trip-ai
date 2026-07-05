"""HTTP 接口压测脚本（对应 Node 版 benchmark-http.ts）

测试端点：
  - POST /api/user/login    登录接口
  - GET  /api/history/trips  历史记录接口（需认证）

使用 asyncio + httpx 实现并发压测，统计 QPS、P50/P95/P99 延迟。
"""

import asyncio
import os
import time

import httpx

from benchmark_lib.auth import get_auth_header, get_eval_credentials, BASE_URL
from benchmark_lib.store import get_env, save_result

CONNECTIONS = int(os.getenv("BENCH_CONNECTIONS", "10"))
DURATION_SEC = int(os.getenv("BENCH_DURATION", "30"))


async def bench_endpoint(client: httpx.AsyncClient, method: str, url: str,
                         body: dict | None = None,
                         headers: dict | None = None) -> list[dict]:
    """对单个端点并发压测"""
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
            elapsed = (time.monotonic() - req_start) * 1000  # ms
            results.append({
                "status": resp.status_code,
                "elapsed_ms": elapsed,
                "success": resp.is_success,
            })
        except Exception as e:
            elapsed = (time.monotonic() - req_start) * 1000
            results.append({"status": 0, "elapsed_ms": elapsed, "success": False, "error": str(e)})

    while time.monotonic() - start_time < DURATION_SEC:
        tasks.append(_request())
        if len(tasks) >= CONNECTIONS:
            await asyncio.gather(*tasks)
            tasks = []

    if tasks:
        await asyncio.gather(*tasks)

    return results


async def main():
    print(f"HTTP Benchmark: {CONNECTIONS} connections × {DURATION_SEC}s")
    print(f"Base URL: {BASE_URL}")

    # 获取认证 token
    print("Getting auth token...")
    auth_headers = get_auth_header(BASE_URL)
    login_body = get_eval_credentials()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        # 登录压测
        print(f"Benchmarking POST /api/user/login ...")
        login_results = await bench_endpoint(
            client, "POST", "/api/user/login", body=login_body
        )

        # 历史记录压测
        print(f"Benchmarking GET /api/history/trips ...")
        history_results = await bench_endpoint(
            client, "GET", "/api/history/trips", headers=auth_headers
        )

    # 统计结果
    def stats(results: list[dict], label: str) -> dict:
        total = len(results)
        success = sum(1 for r in results if r["status"] == 200)
        non2xx = sum(1 for r in results if r["status"] != 0 and r["status"] != 200)
        errors = sum(1 for r in results if r["status"] == 0)
        latencies = [r["elapsed_ms"] for r in results if r["status"] == 200]
        all_latencies = [r["elapsed_ms"] for r in results]

        qps = total / DURATION_SEC
        effective_qps = success / DURATION_SEC if success else 0

        sorted_lat = sorted(latencies) if latencies else [0]

        def pct(p):
            if not sorted_lat:
                return 0
            idx = int((len(sorted_lat) - 1) * p / 100)
            return round(sorted_lat[idx], 2)

        result = {
            "url": f"{BASE_URL.rstrip('/')}/{label.lower().replace(' ', '/').replace('//', '/')}",
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
        print(f"  {label}: QPS={result['effectiveQps']}, P99={result['p99']}ms, "
              f"success={success}/{total}")
        return result

    login_stats = stats(login_results, "login")
    history_stats = stats(history_results, "history")

    result = {
        "scenario": "http",
        "env": get_env(),
        "config": {
            "connections": CONNECTIONS,
            "durationSec": DURATION_SEC,
            "rateLimit": "20 req/min per (IP for login / userId for authed)",
        },
        "login": login_stats,
        "history": history_stats,
        "notes": f"{CONNECTIONS} connections × {DURATION_SEC}s. "
                 "Login triggers rate limit (max=20/min/user). "
                 "qps = totalRequests/duration; effectiveQps = 2xx/duration.",
    }

    save_result("http-results", result)
    print("HTTP benchmark complete.")


if __name__ == "__main__":
    asyncio.run(main())
