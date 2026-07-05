"""多轮 chat cache hit rate 演化测试

对标 Node.js eval/multi-turn-smoke.ts。

流程：
1. 登录拿 token
2. 发 turn 1（无 conversationId），记录 hitRate
3. 发 turn 2（带 conversationId），记录 hitRate
4. 发 turn 3（带 conversationId），记录 hitRate

用法：
  EVAL_BASE_URL=http://127.0.0.1:3000 python -m eval.multi_turn_smoke

输出：每轮的 prompt / cached / hitRate，3 个城市各跑一次
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------

BASE = os.environ.get("EVAL_BASE_URL", "http://127.0.0.1:3000")
USER = os.environ.get("EVAL_USERNAME", "")
PASS = os.environ.get("EVAL_PASSWORD", "")


# ---------------------------------------------------------------------------
# 类型
# ---------------------------------------------------------------------------


@dataclass
class SSEEvent:
    type: str = ""
    content: str | None = None
    error: str | None = None
    data: dict | None = None
    usage: dict | None = None


@dataclass
class TurnResult:
    index: int
    message: str
    prompt: int = 0
    cached: int = 0
    hit_rate: float = 0.0
    duration_ms: int = 0
    error: str | None = None


@dataclass
class Scenario:
    name: str
    turns: list[str]


# ---------------------------------------------------------------------------
# 场景定义
# ---------------------------------------------------------------------------

SCENARIOS: list[Scenario] = [
    Scenario(
        name="chengdu-3days",
        turns=[
            "帮我规划成都3日行程，带父母，慢节奏，喜欢美食和茶馆",
            "第二天能加个火锅吗，父母不太能吃辣",
            "那预算大概多少？三个人",
        ],
    ),
    Scenario(
        name="tokyo-5days",
        turns=[
            "帮我规划东京5日行程，学生党，预算 8000 块",
            "推荐几个免费景点",
            "从机场到新宿怎么走最便宜",
        ],
    ),
    Scenario(
        name="xian-2days-kid",
        turns=[
            "帮我规划西安2日行程，带 6 岁小孩，想看兵马俑但是怕他累",
            "第二天安排轻松点，最好有午休时间",
            "兵马俑附近有适合小孩吃的地方吗",
        ],
    ),
]


# ---------------------------------------------------------------------------
# SSE 解析
# ---------------------------------------------------------------------------


def _parse_sse_event(raw: str) -> SSEEvent | None:
    """解析一条 SSE 事件（多行 data: 拼接）。"""
    data_lines: list[str] = []
    for line in raw.split("\n"):
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return None
    data_str = "\n".join(data_lines)
    try:
        parsed = json.loads(data_str)
        if isinstance(parsed, dict):
            return SSEEvent(
                type=parsed.get("type", ""),
                content=parsed.get("content"),
                data=parsed.get("data"),
                error=parsed.get("error"),
                usage=parsed.get("usage"),
            )
    except json.JSONDecodeError:
        return SSEEvent(type="chunk", content=data_str)
    return None


async def _parse_sse_stream(response: httpx.Response) -> dict[str, Any]:
    """解析 SSE 流，返回 usage/conversationId/error/text。"""
    text = ""
    usage: dict | None = None
    returned_conv_id: int | None = None
    error: str | None = None
    buffer = ""

    async for raw_line in response.aiter_lines():
        buffer += raw_line + "\n"
        while "\n\n" in buffer:
            idx = buffer.index("\n\n")
            raw_event = buffer[:idx]
            buffer = buffer[idx + 2 :]
            if not raw_event.strip():
                continue
            event = _parse_sse_event(raw_event)
            if event is None:
                continue
            if event.type == "chunk" and event.content:
                text += event.content
            elif event.type == "complete":
                if event.data and isinstance(event.data, dict):
                    conv_id = event.data.get("conversationId")
                    if conv_id is not None:
                        returned_conv_id = int(conv_id)
                u = event.usage or (event.data.get("usage") if event.data else None)
                if u and isinstance(u, dict):
                    usage = u
            elif event.type == "error":
                error = event.error or "unknown"

    return {"text": text, "usage": usage, "conversation_id": returned_conv_id, "error": error}


# ---------------------------------------------------------------------------
# 登录 + 单次 chat
# ---------------------------------------------------------------------------


async def login(client: httpx.AsyncClient) -> str:
    """登录拿 JWT token。"""
    resp = await client.post(
        f"{BASE}/api/user/login",
        json={"username": USER, "password": PASS},
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"login failed: {resp.status_code} {resp.text}")
    data = resp.json()
    token = (data.get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"no token in response: {data}")
    return token


async def chat_once(
    client: httpx.AsyncClient,
    token: str,
    message: str,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """调一次 chat 接口（SSE 流）。"""
    body: dict[str, Any] = {"message": message}
    if conversation_id is not None:
        body["conversationId"] = conversation_id

    async with client.stream(
        "POST",
        f"{BASE}/api/trip/chat",
        json=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    ) as resp:
        if resp.status_code != 200:
            await resp.aread()
            return {"error": f"chat failed: {resp.status_code}", "text": ""}
        return await _parse_sse_stream(resp)


# ---------------------------------------------------------------------------
# 跑一个场景
# ---------------------------------------------------------------------------


async def run_scenario(
    client: httpx.AsyncClient, token: str, scenario: Scenario
) -> list[TurnResult]:
    results: list[TurnResult] = []
    conversation_id: int | None = None

    for i, message in enumerate(scenario.turns):
        start = time.monotonic()
        r = await chat_once(client, token, message, conversation_id)
        duration_ms = int((time.monotonic() - start) * 1000)

        if r.get("error"):
            results.append(
                TurnResult(
                    index=i + 1,
                    message=message,
                    duration_ms=duration_ms,
                    error=r["error"],
                )
            )
            break

        if r.get("conversation_id"):
            conversation_id = r["conversation_id"]

        usage = r.get("usage") or {}
        prompt = usage.get("prompt", 0) or usage.get("input_tokens", 0)
        cached = usage.get("cached", 0) or usage.get("cache_read", 0)
        hit_rate = cached / prompt if prompt > 0 else 0.0

        results.append(
            TurnResult(
                index=i + 1,
                message=message,
                prompt=prompt,
                cached=cached,
                hit_rate=hit_rate,
                duration_ms=duration_ms,
            )
        )

    return results


# ---------------------------------------------------------------------------
# 格式化输出
# ---------------------------------------------------------------------------


def _hit_emoji(rate: float) -> str:
    if rate >= 0.5:
        return "🟢"
    if rate >= 0.3:
        return "🟡"
    return "🔴"


def print_results(all_results: dict[str, list[TurnResult]]) -> None:
    for name, results in all_results.items():
        print(f"━━━ {name} ━━━")
        for r in results:
            if r.error:
                print(f"  turn {r.index}  ❌ {r.error}  ({r.duration_ms}ms)")
            else:
                pct = f"{r.hit_rate * 100:.1f}"
                color = _hit_emoji(r.hit_rate)
                print(
                    f"  turn {r.index}  {color} hitRate={pct}%  "
                    f"prompt={r.prompt:,}  cached={r.cached:,}  "
                    f"({r.duration_ms}ms)"
                )
        print()

    # 汇总表
    print("━━━ summary ━━━")
    print("scenario        | turn1    | turn2    | turn3    | avg")
    for name, rs in all_results.items():
        cells = []
        for i in range(3):
            if i < len(rs):
                cells.append(f"{rs[i].hit_rate * 100:.1f}%")
            else:
                cells.append("n/a")
        valid = [r for r in rs if not r.error]
        avg = (
            f"{sum(r.hit_rate for r in valid) / len(valid) * 100:.1f}%"
            if valid
            else "n/a"
        )
        row = f"{name:<15} | {cells[0]:<8} | {cells[1]:<8} | {cells[2]:<8} | {avg}"
        print(row)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def amain() -> None:
    print(f"Multi-turn smoke test → {BASE}\n")
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        token = await login(client)
        print("logged in.\n")

        all_results: dict[str, list[TurnResult]] = {}
        for scenario in SCENARIOS:
            results = await run_scenario(client, token, scenario)
            all_results[scenario.name] = results

    print_results(all_results)


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print("\ninterrupted.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
