#!/usr/bin/env python3
"""真实对话测试：ChatAgent 需求补全功能验收。

运行前确保：
1. 后端服务已启动（uvicorn src.main:app --reload，端口 8000）
2. 已注册用户并有有效 token（或通过测试方式绕过认证）

测试场景：
- 场景 1：输入"周末想出去逛逛" → 应返回 clarify card
- 场景 2：补全"北京,2天,3000元" → 应进入规划流程
- 场景 3：完整输入"去成都玩3天，预算4000" → 直接规划，无 clarify
"""

import asyncio
import json
import sys
from typing import Any

import httpx

# 后端 API 地址
BASE_URL = "http://localhost:8000"

# 测试用户（需提前注册或通过测试方式创建）
TEST_USER = {
    "username": "test_user",
    "password": "Test@123456",
    "email": "test@example.com",
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
        return data.get("data", {}).get("token")

    # 登录失败 → 尝试注册
    resp = await client.post(f"{BASE_URL}/api/user/register", json={
        "username": TEST_USER["username"],
        "password": TEST_USER["password"],
        "email": TEST_USER["email"],
        "nickname": "Test User",
    })
    if resp.status_code in (200, 201):
        # 注册成功 → 再次登录
        resp = await client.post(f"{BASE_URL}/api/user/login", json={
            "username": TEST_USER["username"],
            "password": TEST_USER["password"],
        })
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("token")

    print(f"⚠️ 认证失败: {resp.status_code} {resp.text[:200]}")
    return None


async def chat_stream(client: httpx.AsyncClient, token: str, message: str) -> dict[str, Any]:
    """发送对话请求，收集 SSE 事件。"""
    headers = {"Authorization": f"Bearer {token}"}
    events: list[dict] = []

    async with client.stream(
        "POST",
        f"{BASE_URL}/api/trip/chat",
        headers=headers,
        json={"message": message},
        timeout=60.0,
    ) as resp:
        if resp.status_code != 200:
            text = await resp.aread()
            return {"error": f"HTTP {resp.status_code}: {text.decode()[:200]}"}

        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]  # strip "data: "
            try:
                event = json.loads(raw)
                events.append(event)
            except json.JSONDecodeError:
                pass

    return {"events": events}


def check_clarify_card(events: list[dict]) -> bool:
    """检查是否发出 clarify card。"""
    for ev in events:
        if ev.get("card_type") == "clarify":
            return True
    return False


def check_trip_planned(events: list[dict]) -> bool:
    """检查是否发出 trip_planned 事件。"""
    for ev in events:
        if ev.get("type") == "trip_planned":
            return True
    return False


def print_result(scenario: str, result: dict):
    """打印测试结果。"""
    if "error" in result:
        print(f"  ❌ {scenario}: {result['error']}")
        return False

    events = result.get("events", [])
    has_clarify = check_clarify_card(events)
    has_trip_planned = check_trip_planned(events)

    # 打印事件摘要
    for ev in events[:5]:  # 只打印前 5 个事件
        etype = ev.get("type", "?")
        card_type = ev.get("card_type", "")
        if card_type:
            print(f"    event: {etype} card_type={card_type}")
        else:
            print(f"    event: {etype}")

    return has_clarify, has_trip_planned


async def main():
    async with httpx.AsyncClient() as client:
        # 1. 认证
        print("🔐 认证...")
        token = await get_or_create_token(client)
        if not token:
            print("❌ 认证失败，请确保后端已启动且可注册/登录")
            return 1
        print("  ✅ 认证成功")

        # 2. 场景 1：输入不完整 → 应返回 clarify card
        print("\n📋 场景 1：输入"周末想出去逛逛" → 应返回 clarify card")
        result1 = await chat_stream(client, token, "周末想出去逛逛")
        has_clarify1, has_trip1 = print_result("场景 1", result1)
        if has_clarify1:
            print("  ✅ 场景 1 通过：发出 clarify card")
        else:
            print("  ❌ 场景 1 失败：未发出 clarify card")

        # 3. 场景 2：补全字段 → 应进入规划（直接规划，不再 clarify）
        print("\n📋 场景 2：补全"北京,2天,3000元" → 应进入规划")
        result2 = await chat_stream(client, token, "目的地:北京\n天数:2\n预算:3000")
        has_clarify2, has_trip2 = print_result("场景 2", result2)
        if not has_clarify2 and has_trip2:
            print("  ✅ 场景 2 通过：无 clarify，直接 trip_planned")
        else:
            print(f"  ⚠️ 场景 2 部分通过：clarify={has_clarify2}, trip_planned={has_trip2}")

        # 4. 场景 3：完整输入 → 直接规划
        print("\n📋 场景 3：完整输入"去成都玩3天，预算4000" → 直接规划")
        result3 = await chat_stream(client, token, "去成都玩3天，预算4000")
        has_clarify3, has_trip3 = print_result("场景 3", result3)
        if not has_clarify3 and has_trip3:
            print("  ✅ 场景 3 通过：无 clarify，直接 trip_planned")
        else:
            print(f"  ⚠️ 场景 3 部分通过：clarify={has_clarify3}, trip_planned={has_trip3}")

        # 汇总
        print("\n" + "="*50)
        passed = sum([
            has_clarify1,
            not has_clarify2 and has_trip2,
            not has_clarify3 and has_trip3,
        ])
        print(f"结果：{passed}/3 场景通过")
        return 0 if passed == 3 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
