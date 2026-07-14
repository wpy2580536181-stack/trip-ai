"""
Real Agent 调用器

通过 HTTP 调 /api/trip/chat，收集 SSE 流，组装为 AgentOutput。
多轮 fixture 自动处理：先发 history 里的 user 消息建立 conversationId，再发当前 message。

设计要点：
1) 鉴权：用测试账号登录拿 JWT token，缓存在实例
2) SSE 解析：逐行读取 data: 前缀
3) toolCalls：tool_start + tool_end 配对
4) JSON 提取：流结束后从 text 中提取 JSON
5) 错误处理：SSE error 事件 → AgentOutput.error
6) 超时：默认 90s（agent 60s + LLM 余量 + RAG + 网络）
7) 重试：429/5xx/网络错误 → 3 次重试，间隔 3s/6s/9s
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from httpx import AsyncHTTPTransport

from eval.types import AgentOutput, Fixture, TokenUsage, ToolCall

logger = logging.getLogger("real-agent")


# ==================================================================
# JSON 提取（从 LLM 输出中提取嵌在文本里的 JSON）
# ==================================================================


def _extract_json(text: str) -> dict | None:
    """从文本中提取第一个合法的 JSON 对象。"""
    # 1. 尝试直接解析
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. 找最外层 { ... } 配对
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1
    return None


# ==================================================================
# SSE 事件
# ==================================================================


@dataclass
class _SSEEvent:
    type: str = ""
    content: str | None = None
    name: str | None = None
    data: dict | None = None
    output: str | None = None
    error: str | None = None
    usage: dict | None = None


def _parse_one_sse_event(raw: str) -> _SSEEvent | None:
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
            return _SSEEvent(
                type=parsed.get("type", ""),
                content=parsed.get("content"),
                name=parsed.get("name"),
                data=parsed.get("data"),
                output=parsed.get("output"),
                error=parsed.get("error"),
                usage=parsed.get("usage"),
            )
    except json.JSONDecodeError:
        # 非 JSON 当 chunk
        return _SSEEvent(type="chunk", content=data_str)
    return None


async def _parse_sse_stream(response: httpx.Response) -> dict[str, Any]:
    """解析 SSE 流，返回 text/toolCalls/error/conversationId/usage。"""
    text = ""
    tool_calls: list[ToolCall] = []
    error: str | None = None
    returned_conv_id: int | None = None
    usage: TokenUsage | None = None
    open_tool_names: list[str] = []
    open_tool_with_output: list[dict] = []  # 暂存 tool_start/tool_end 配对信息

    buffer = ""
    try:
        async for raw_line in response.aiter_lines():
            # httpx aiter_lines strips trailing \n but we accumulate in buffer
            buffer += raw_line + "\n"

            # 按 \n\n 切分完整事件
            while "\n\n" in buffer:
                idx = buffer.index("\n\n")
                raw_event = buffer[:idx]
                buffer = buffer[idx + 2 :]
                if not raw_event.strip():
                    continue

                event = _parse_one_sse_event(raw_event)
                if event is None:
                    continue

                if event.type == "chunk":
                    if event.content:
                        text += event.content
                elif event.type == "tool_start":
                    if event.name:
                        open_tool_names.append(event.name)
                        open_tool_with_output.append({"name": event.name, "output": None, "args": None})
                elif event.type == "tool_end":
                    name = open_tool_names.pop() if open_tool_names else (event.name or "unknown")
                    # 合并配对信息：捕获 tool 输出
                    tool_output = event.output or (event.data.get("output") if event.data and isinstance(event.data, dict) else None)
                    tool_call = ToolCall(name=name, timestamp=datetime.now(timezone.utc).isoformat())
                    if tool_output:
                        tool_call.result = str(tool_output)[:5000]  # 截断过长输出
                    tool_calls.append(tool_call)
                elif event.type == "complete":
                    if event.data and isinstance(event.data, dict):
                        conv_id = event.data.get("conversationId")
                        if conv_id is not None:
                            returned_conv_id = int(conv_id)
                    # 如果 chunk 事件没有累积到文本，从 complete 事件中提取
                    if not text.strip() and event.content:
                        text = event.content
                    u = event.usage or (event.data.get("usage") if event.data else None)
                    if u and isinstance(u, dict):
                        usage = TokenUsage(
                            prompt=u.get("prompt", 0) or u.get("input_tokens", 0),
                            completion=u.get("completion", 0) or u.get("output_tokens", 0),
                            total=u.get("total", 0) or u.get("total_tokens", 0),
                            cached=u.get("cached", 0) or u.get("cache_read", 0),
                        )
                elif event.type == "error":
                    error = event.error or "未知错误"
    except Exception as e:
        error = str(e)

    return {
        "text": text,
        "tool_calls": tool_calls,
        "error": error,
        "conversation_id": returned_conv_id,
        "usage": usage,
    }


# ==================================================================
# RealAgent
# ==================================================================


@dataclass
class RealAgentOptions:
    base_url: str = "http://127.0.0.1:8000"
    username: str = ""
    password: str = ""
    timeout_ms: int = 90000
    delay_between_ms: int = 2000
    max_retries: int = 3


class RealAgent:
    """通过 HTTP 调用真实 Agent 接口。"""

    def __init__(self, options: RealAgentOptions | None = None, **kwargs: Any) -> None:
        if options is not None:
            self._opts = options
        else:
            self._opts = RealAgentOptions(**kwargs)
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            timeout_s = self._opts.timeout_ms / 1000.0
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_s, connect=30.0),
                # 显式禁用代理，避免 HTTP_PROXY 环境变量干扰
                mounts={
                    "all://": httpx.AsyncHTTPTransport(proxy=None),
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def delay(self) -> None:
        """fixture 之间延迟，避免触发后端 rate limit。"""
        if self._opts.delay_between_ms > 0:
            await asyncio.sleep(self._opts.delay_between_ms / 1000.0)

    async def login(self) -> str:
        """登录拿 JWT token。"""
        if self._token:
            return self._token

        client = self._get_client()
        resp = await client.post(
            f"{self._opts.base_url}/api/user/login",
            json={"username": self._opts.username, "password": self._opts.password},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"登录失败 ({resp.status_code}): {resp.text}")

        data = resp.json()
        token = (data.get("data") or {}).get("token")
        if not token:
            raise RuntimeError(f"登录响应无 token: {data}")

        self._token = token
        logger.info("登录成功，token 前缀 %s...", token[:20])
        return token

    async def _chat_once(
        self, message: str, conversation_id: int | None = None
    ) -> dict[str, Any]:
        """调一次 chat 接口（含重试）。"""
        last_err: Exception | None = None
        for attempt in range(self._opts.max_retries + 1):
            try:
                return await self._chat_once_no_retry(message, conversation_id)
            except Exception as e:
                last_err = e
                msg = str(e)
                is_retryable = bool(re.search(r"429|5\d\d|超时|aborted|network|connect", msg, re.IGNORECASE))
                if not is_retryable or attempt >= self._opts.max_retries:
                    raise
                wait = 3.0 * (attempt + 1)
                logger.warning("[chat] 第 %d 次失败，%.0fs 后重试：%s", attempt + 1, wait, msg[:100])
                await asyncio.sleep(wait)
        raise last_err  # type: ignore[misc]

    async def _chat_once_no_retry(
        self, message: str, conversation_id: int | None = None
    ) -> dict[str, Any]:
        """调一次 chat 接口（不含重试）。"""
        token = await self.login()
        start = asyncio.get_event_loop().time()

        client = self._get_client()
        body: dict[str, Any] = {"message": message}
        if conversation_id is not None:
            body["conversationId"] = conversation_id

        async with client.stream(
            "POST",
            f"{self._opts.base_url}/api/trip/chat",
            json=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        ) as resp:
            if resp.status_code != 200:
                await resp.aread()
                raise RuntimeError(f"chat 接口错误 ({resp.status_code}): {resp.text}")

            sse_result = await _parse_sse_stream(resp)

        duration_ms = int((asyncio.get_event_loop().time() - start) * 1000)
        sse_result["duration_ms"] = duration_ms

        # 提取 JSON
        text = sse_result["text"]
        sse_result["json"] = _extract_json(text) if text else None

        return sse_result

    async def run(self, fixture: Fixture) -> AgentOutput:
        """跑一个 fixture：

        - 如果有 history，先逐条发 user 消息建立多轮
        - 然后发当前 message 拿最终输出
        """
        conversation_id: int | None = None

        # 1) 多轮准备：发 history 里的 user 消息
        if fixture.input.history:
            logger.info("[%s] 多轮准备：%d 条 history", fixture.id, len(fixture.input.history))
            for turn in fixture.input.history:
                if turn.get("role") != "user":
                    continue
                try:
                    result = await self._chat_once(turn["content"], conversation_id)
                    conversation_id = result.get("conversation_id")
                except Exception as e:
                    logger.warning("[%s] history turn 失败: %s（继续）", fixture.id, e)

        # 2) 发当前 message
        logger.info("[%s] 跑主问题", fixture.id)
        try:
            result = await self._chat_once(fixture.input.message, conversation_id)
            return AgentOutput(
                text=result.get("text", ""),
                json=result.get("json"),
                tool_calls=result.get("tool_calls", []),
                error=result.get("error"),
                tokens=result.get("usage"),
                duration_ms=result.get("duration_ms", 0),
                conversation_id=result.get("conversation_id"),
            )
        except Exception as e:
            msg = str(e)
            logger.error("[%s] 主问题失败: %s", fixture.id, msg)
            return AgentOutput(
                text="",
                tool_calls=[],
                error=msg,
                duration_ms=0,
            )
