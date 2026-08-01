#!/usr/bin/env python3
"""
真实对话测试脚本：ChatAgent 需求补全功能验收

用法：
  # 1. 确保后端已启动（端口 8000）
  cd trip-backend && .venv/bin/python -m uvicorn src.main:app --reload &

  # 2. 运行测试
  .venv/bin/python trip-backend/test_real_clarify_flow.py

注意：需要先注册/登录获取 token。脚本会自动注册测试用户。
"""

import asyncio
import json
import sys
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
TEST_USER = {
    "username": "clarify_test_user",
    "password": "Test@123456",
    "email": "clarify_test@example.com",
}


async def get_or_create_token(client: httpx.AsyncClient) -> str | None:
    """获取或创建测试用户 token。"""
    # 尝试登录
    resp = await client.post(f"{BASE_URL}/api/user/login", json={
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
    })
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("data", {}).get("token")
        if token:
            return token

    # 注册
    resp = await client.post(f"{BASE_URL}/api/user/register", json={
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
        "email": TEST_USER["email"],
        "nickname": "Clarify Test User",
    })
    if resp.status_code in (200, 201):
        # 登录
        resp = await client.post(f"{BASE_URL}/api/user/login", json={
            "username": TEST_USER["username"],
            "password": TEST_USER["password"],
        })
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("token")

    return None


async def chat_and_collect(client: httpx.AsyncClient, token: str, message: str) -> dict[str, Any]:
    """发送对话请求，收集所有 SSE 事件。"""
    headers = {"Authorization": f"Bearer {token}"}
    events: list[dict] = []

    try:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/trip/chat",
            headers=headers,
            json={"message": message},
            timeout=120.0,
        ) as resp:
            if resp.status_code != 200:
                text = await resp.aread()
                return {"error": f"HTTP {resp.status_code}: {text.decode()[:300]}"}

            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        return {"error": str(e)}

    return {"events": events, "count": len(events)}


def check_clarify_card(events: list[dict]) -> bool:
    """检查是否发出 clarify card event。"""
    return any(ev.get("card_type") == "clarify" for ev in events)


def check_trip_planned(events: list[dict]) -> bool:
    """检查是否发出 trip_planned event。"""
    return any(ev.get("type") == "trip_planned" for ev in events)


def print_summary(scenario: str, events: list[dict], expect_clarify: bool, expect_planned: bool):
    """打印测试摘要。"""
    has_clarify = check_clarify_card(events)
    has_planned = check_trip_planned(events)

    # 打印事件类型
    for ev in events[:8]:
        etype = ev.get("type", "?")
        card = ev.get("card_type", "")
        if card:
            print(f"    [{etype} | card={card}]")
        else:
            print(f"    [{etype}]")

    ok = (has_clarify == expect_clarify) and (has_planned == expect_planned)
    status = "✅ PASS" if ok else "❌ FAIL"
    print(f"  {status} | clarify={has_clarify} (exp={expect_clarify}) | trip_planned={has_planned} (exp={expect_planned})")
    return ok


async def run_tests() -> int:
    """运行所有测试场景。"""
    async with httpx.AsyncClient() as client:
        # 1. 认证
        print("🔐 认证中...")
        token = await get_or_create_token(client)
        if not token:
            print("❌ 认证失败（后端是否启动？）")
            return 1
        print(f"  ✅ 认证成功（token={token[:20]}...）")

        results: list[bool] = []

        # 场景 1：不完整输入 → 应返回 clarify card
        print("\n📋 场景 1：输入"周末想出去逛逛"")
        print("  预期：发出 clarify card（city/days/budget 缺失）")
        r1 = await chat_and_collect(client, token, "周末想出去逛逛")
        if "error" in r1:
            print(f"  ❌ 请求失败: {r1['error']}")
            results.append(False)
        else:
            results.append(print_summary("场景 1", r1["events"], expect_clarify=True, expect_planned=False))

        # 场景 2：补全字段 → 应进入规划
        print("\n📋 场景 2：补全"目的地:北京\\n天数:2\\n预算:3000"")
        print("  预期：无 clarify card，触发 Orchestrator（trip_planned）")
        r2 = await chat_and_collect(client, token, "目的地:北京\n天数:2\n预算:3000")
        if "error" in r2:
            print(f"  ❌ 请求失败: {r2['error']}")
            results.append(False)
        else:
            results.append(print_summary("场景 2", r2["events"], expect_clarify=False, expect_planned=True))

        # 场景 3：完整输入 → 直接规划
        print("\n📋 场景 3：完整输入"去成都玩3天，预算4000"")
        print("  预期：无 clarify card，直接规划")
        r3 = await chat_and_collect(client, token, "去成都玩3天，预算4000")
        if "error" in r3:
            print(f"  ❌ 请求失败: {r3['error']}")
            results.append(False)
        else:
            results.append(print_summary("场景 3", r3["events"], expect_clarify=False, expect_planned=True))

        # 汇总
        print("\n" + "="*60)
        passed = sum(results)
        total = len(results)
        print(f"测试结果：{passed}/{total} 场景通过")

        if passed == total:
            print("🎉 所有场景通过！需求补全功能验收成功。")
            return 0
        else:
            print("⚠️ 部分场景未通过，请检查实现。")
            return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n中断")
        sys.exit(130)
