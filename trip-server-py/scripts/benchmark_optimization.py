"""优化效果验证压测 — 专注 /recommend API 耗时对比。

测试场景：
1. Cold cache — 不同城市，验证 POI 缓存冷启动耗时
2. Warm cache — 同一城市重复请求，验证缓存命中加速（含 Research Bundle 全量缓存）
3. LLM cache — 完全相同的请求参数，验证 LLM 缓存命中
4. SSE stream — 验证 recommend-stream SSE 端点首字节时间 + 总耗时
"""

import asyncio
import json
import os
import time
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# 关闭限流
os.environ["RATE_LIMIT_AUTH_MAX"] = "99999"
os.environ["RATE_LIMIT_GLOBAL_MAX"] = "999999"
os.environ["RATE_LIMIT_CHAT_MAX"] = "99999"
os.environ["RATE_LIMIT_RECOMMEND_MAX"] = "99999"

BASE_URL = "http://localhost:3000"
LOGIN = {"username": "eval-test", "password": "EvalTest@2026"}


@dataclass
class Result:
    request_id: int
    city: str
    days: int
    budget: int
    status: int
    duration_ms: float
    error: str = ""


@dataclass
class Summary:
    label: str
    results: list[Result] = field(default_factory=list)

    def stats(self) -> dict:
        if not self.results:
            return {"label": self.label, "count": 0}
        durations = sorted(r.duration_ms for r in self.results if r.status == 200)
        if not durations:
            return {"label": self.label, "count": 0, "errors": len(self.results)}
        return {
            "label": self.label,
            "count": len(durations),
            "errors": len(self.results) - len(durations),
            "min_ms": round(min(durations)),
            "p50_ms": round(statistics.median(durations)),
            "p95_ms": round(statistics.quantiles(durations, n=20)[18], 0) if len(durations) >= 20 else durations[-1],
            "max_ms": round(max(durations)),
            "mean_ms": round(statistics.mean(durations)),
        }


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE_URL}/api/user/login", json=LOGIN, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"Login failed: {r.status_code} {r.text}")
    return r.json()["data"]["token"]


async def recommend(client: httpx.AsyncClient, token: str, request_id: int,
                   city: str, days: int, budget: int) -> Result:
    t0 = time.time()
    try:
        r = await client.post(
            f"{BASE_URL}/api/trip/recommend",
            json={"city": city, "days": days, "budget": budget},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )
        duration_ms = (time.time() - t0) * 1000
        return Result(request_id, city, days, budget, r.status_code, duration_ms,
                     error="" if r.status_code == 200 else r.text[:200])
    except Exception as e:
        return Result(request_id, city, days, budget, 0, (time.time() - t0) * 1000, str(e)[:200])


async def recommend_stream(client: httpx.AsyncClient, token: str, request_id: int,
                          city: str, days: int, budget: int) -> dict:
    """测试 SSE /recommend-stream 端点：记录首字节时间 + 总耗时 + complete 事件。"""
    t0 = time.time()
    first_event_time = None
    result_data = {}
    try:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/trip/recommend-stream",
            json={"city": city, "days": days, "budget": budget},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        ) as resp:
            async for line in resp.aiter_lines():
                if first_event_time is None:
                    first_event_time = (time.time() - t0) * 1000  # TTFB (首字节时间)
                if line.startswith("data:") and event_type == "complete":
                    try:
                        result_data = json.loads(line[5:])
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        return Result(request_id, city, days, budget, 0, (time.time() - t0) * 1000, str(e)[:200])
    
    total_ms = (time.time() - t0) * 1000
    return {
        "id": request_id, "city": city, "days": days, "budget": budget,
        "ttfb_ms": round(first_event_time or total_ms),
        "total_ms": round(total_ms),
        "success": "complete" in str(result_data),
    }


async def run_test(label: str, token: str, city_specs: list[tuple[str, int, int]],
                   repeat: int = 1) -> Summary:
    summary = Summary(label)
    async with httpx.AsyncClient() as client:
        rid = 0
        for city, days, budget in city_specs:
            for r in range(repeat):
                rid += 1
                result = await recommend(client, token, rid, city, days, budget)
                summary.results.append(result)
                status = "✅" if result.status == 200 else "❌"
                print(f"    [{rid}] {status} {city} {days}天 {budget}元 → {result.duration_ms:.0f}ms {result.error[:80] if result.error else ''}")
    return summary


async def main():
    # Step 1: Login
    print("🔑 登录中...")
    async with httpx.AsyncClient() as client:
        token = await login(client)
        print("✅ 登录成功\n")

    summaries = []

    # ── Scenario 1: Cold Cache（不同城市，每个城市首次请求） ──
    cold_cities = [
        ("三亚", 3, 5000),
        ("桂林", 4, 4000),
        ("昆明", 3, 3000),
        ("重庆", 2, 2500),
        ("南京", 3, 3500),
    ]
    print("🧊 Scenario 1: Cold Cache — 5 个不同城市（首次请求）")
    s = await run_test("Cold Cache (5 cities × 1)", token, cold_cities, repeat=1)
    summaries.append(s)
    print(f"   完成: {len([r for r in s.results if r.status == 200])}/{len(s.results)} 成功")

    # ── Scenario 2: Warm Cache（同一城市重复请求，POI 缓存命中） ──
    warm_spec = [("北京", 3, 6000)]
    print("\n🔥 Scenario 2: Warm Cache — 同一城市重复 5 次")
    s = await run_test("Warm Cache (1 city × 5)", token, warm_spec, repeat=5)
    summaries.append(s)
    ok = [r for r in s.results if r.status == 200]
    if ok:
        if len(ok) >= 2:
            print(f"   首次: {ok[0].duration_ms:.0f}ms → 第2次: {ok[1].duration_ms:.0f}ms", end="")
        else:
            print(f"   仅 {len(ok)} 次成功: {ok[0].duration_ms:.0f}ms", end="")
        if len(ok) >= 5:
            print(f" → 第5次: {ok[-1].duration_ms:.0f}ms")
        else:
            print()
    print(f"   完成: {len(ok)}/{len(s.results)} 成功")

    # ── Scenario 3: LLM Cache（完全相同的请求参数） ──
    print("\n🧠 Scenario 3: LLM Cache — 完全相同的参数重复 3 次")
    s = await run_test("LLM Cache (same params × 3)", token, [("三亚", 3, 5000)], repeat=3)
    summaries.append(s)
    ok = [r for r in s.results if r.status == 200]
    if len(ok) >= 2:
        print(f"   首次: {ok[0].duration_ms:.0f}ms → 第2次: {ok[1].duration_ms:.0f}ms", end="")
        if len(ok) >= 3:
            print(f" → 第3次: {ok[2].duration_ms:.0f}ms")
        else:
            print()
    elif ok:
        print(f"   仅 {len(ok)} 次成功: {ok[0].duration_ms:.0f}ms")
    print(f"   完成: {len(ok)}/{len(s.results)} 成功")

    # ── Report ──
    print("\n" + "=" * 70)
    print("📊 压测结果汇总")
    print("=" * 70)
    for s in summaries:
        st = s.stats()
        if "p50_ms" in st:
            print(f"\n  {st['label']}:")
            print(f"    P50={st['p50_ms']}ms  P95={st['p95_ms']}ms  "
                  f"Min={st['min_ms']}ms  Max={st['max_ms']}ms  "
                  f"Err={st['errors']}/{st['count']+st['errors']}")
        else:
            print(f"\n  {st['label']}: ALL FAILED ({st.get('errors', st.get('count', '?'))} errors)")

    # Write results to JSON
    output_dir = Path(__file__).resolve().parent.parent / "docs" / "performance-data"
    output_dir.mkdir(exist_ok=True)
    result_data = []
    for s in summaries:
        result_data.append(s.stats())
        result_data[-1]["details"] = [
            {"id": r.request_id, "city": r.city, "duration_ms": r.duration_ms,
             "status": r.status, "error": r.error}
            for r in s.results
        ]
    output_file = output_dir / "optimization-results.json"
    output_file.write_text(json.dumps(result_data, indent=2, ensure_ascii=False))
    print(f"\n📁 详细结果已保存: {output_file}")

    # Quick comparison
    cold_ok = [r for r in summaries[0].results if r.status == 200]
    warm_ok = [r for r in summaries[1].results if r.status == 200]
    llm_ok = [r for r in summaries[2].results if r.status == 200]
    
    print(f"\n🎯 优化效果:")
    if cold_ok:
        cold_avg = statistics.mean(r.duration_ms for r in cold_ok)
        print(f"   Cold Cache 平均:  {cold_avg:.0f}ms ({len(cold_ok)}/{len(summaries[0].results)} 成功)")
    
    if warm_ok:
        if len(warm_ok) >= 2:
            warm_1st = warm_ok[0].duration_ms
            warm_2nd = warm_ok[1].duration_ms
            speedup = warm_1st / warm_2nd if warm_2nd > 0 else 0
            print(f"   Warm Cache 首次:  {warm_1st:.0f}ms")
            print(f"   Warm Cache 第2次: {warm_2nd:.0f}ms")
            print(f"   POI 缓存加速比:   {speedup:.1f}x")
        elif warm_ok:
            print(f"   Warm Cache: {warm_ok[0].duration_ms:.0f}ms ({len(warm_ok)}/{len(summaries[1].results)} 成功)")

    if llm_ok:
        if len(llm_ok) >= 2:
            llm_1st = llm_ok[0].duration_ms
            llm_2nd = llm_ok[1].duration_ms
            llm_speedup = llm_1st / llm_2nd if llm_2nd > 0 else 0
            print(f"   LLM Cache 首次:  {llm_1st:.0f}ms")
            print(f"   LLM Cache 第2次: {llm_2nd:.0f}ms")
            print(f"   LLM 缓存加速比:  {llm_speedup:.1f}x")
        elif llm_ok:
            print(f"   LLM Cache: {llm_ok[0].duration_ms:.0f}ms ({len(llm_ok)}/{len(summaries[2].results)} 成功)")


if __name__ == "__main__":
    asyncio.run(main())
