"""HTTP 出站重试工具 — 针对上游 429 限流的退避重访。

设计要点：
- 优先使用服务端下发的 ``Retry-After`` 头指定的等待秒数
- 无 ``Retry-After`` 时采用指数退避兜底（``backoff_base * 2**attempt``，封顶 ``backoff_cap``）
- 仅对 429 重试；非 429 响应直接返回，交由调用方决定降级策略
- 重试次数有上限，避免限流期间形成重试风暴（雪崩）
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """解析 ``Retry-After`` 头，返回等待秒数。

    当前支持纯秒数形式（如 ``"30"``）。HTTP-date 形式在需要时再扩展。
    无法解析时返回 ``None``。
    """
    if not value:
        return None
    value = value.strip()
    try:
        secs = float(value)
    except (ValueError, TypeError):
        return None
    if secs < 0:
        return None
    return secs


async def http_with_retry_on_429(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_cap: float = 30.0,
    **kwargs,
) -> httpx.Response:
    """对上游 429 做退避重试，返回最后的响应对象。

    - 响应非 429：立即返回（调用方自行处理 2xx/4xx/5xx 降级）
    - 响应为 429：等待后重试，最多 ``max_attempts`` 次
    - 重试耗尽仍返回最后一份响应（通常仍为 429），由调用方降级

    Args:
        client: 已配置的 httpx.AsyncClient
        method: HTTP 方法（"GET" / "POST" ...）
        url: 请求 URL
        max_attempts: 最大尝试次数（含首次），默认 3
        backoff_base: 指数退避基数（秒），默认 1.0
        backoff_cap: 单次退避封顶（秒），默认 30.0
        **kwargs: 透传给 ``client.request``（如 params / headers / json）
    """
    last_resp: Optional[httpx.Response] = None
    for attempt in range(max_attempts):
        resp = await client.request(method, url, **kwargs)
        last_resp = resp
        if resp.status_code != 429:
            return resp

        delay = parse_retry_after(resp.headers.get("Retry-After"))
        if delay is None:
            delay = min(backoff_base * (2 ** attempt), backoff_cap)

        logger.warning(
            "upstream_429_retry",
            extra={
                "url": url,
                "attempt": attempt,
                "retry_after": delay,
                "max_attempts": max_attempts,
            },
        )
        await asyncio.sleep(delay)

    return last_resp  # type: ignore[return-value]
