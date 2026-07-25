"""Prometheus metrics 中间件 + 工具函数。

M5 改造：暴露 HTTP 请求 QPS / 延迟 / 错误率等核心指标，
供 K8s Prometheus 自动抓取（端点 `/metrics`）。

设计要点：
- ASGI 中间件（不缓冲响应体，兼容 SSE 流式接口）—— 参考 RequestIDMiddleware
- 4 类核心指标：
  1. http_requests_total{method, path, status}  - Counter，QPS + 错误率
  2. http_request_duration_seconds{method, path} - Histogram，P50/P99 延迟
  3. chat_request_duration_seconds - Histogram，chat 流式 P99
  4. tool_invocations_total{tool, status} - Counter，agent tool 调用
- `/metrics` 端点用 prometheus_client.generate_latest() 输出

面试故事：
- "我的项目用 3 类可观测信号：日志（排错）+ metrics（告警）+ trace（链路）"
- "4 个核心指标覆盖了 QPS / P99 / 错误率 / 业务量"
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.utils.logger import trip_log


# ---------------------------------------------------------------------------
# 指标定义（模块级单例）
# ---------------------------------------------------------------------------

# HTTP 请求计数：method + path 模板（避免高基数）+ status
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)

# HTTP 请求延迟：Histogram 默认 buckets（5ms ~ 10s），P50/P99 直接 histogram_quantile
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Chat 接口单独打点：流式响应 P99 重要指标
chat_request_duration_seconds = Histogram(
    "chat_request_duration_seconds",
    "Chat stream request duration in seconds",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

# Agent tool 调用计数：观察哪个 tool 用得多 / 失败率高
tool_invocations_total = Counter(
    "tool_invocations_total",
    "Total agent tool invocations",
    labelnames=("tool", "status"),  # status: success / failure
)


# ---------------------------------------------------------------------------
# 辅助函数（业务代码调用）
# ---------------------------------------------------------------------------

def record_chat_duration(duration_s: float) -> None:
    """记录 chat 流式响应总耗时（chat controller 调用）。"""
    chat_request_duration_seconds.observe(duration_s)


def record_tool_invocation(tool_name: str, success: bool) -> None:
    """记录 agent tool 调用结果（agent tools 内部调用）。"""
    tool_invocations_total.labels(
        tool=tool_name, status="success" if success else "failure",
    ).inc()


# ---------------------------------------------------------------------------
# ASGI Middleware：自动记录所有 HTTP 请求
# ---------------------------------------------------------------------------

# 排除 /metrics 自身（避免 metrics 抓取被 metrics 记录，无限循环）
# 注意：只排除完全等于 /health 的路径，/health/detail 仍要记录
EXCLUDE_PATHS = ("/metrics", "/health")


class PrometheusMiddleware:
    """ASGI middleware：自动记录 HTTP 请求 QPS + 延迟 + 状态码。

    用 ASGI 实现（不缓冲响应体，兼容 SSE 流式接口）—— 参考 RequestIDMiddleware。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # 排除 metrics 抓取 + health check 自身（注意：只精确等于 /health，/health/detail 仍记录）
        if path in EXCLUDE_PATHS:
            await self.app(scope, receive, send)
            return

        # 用 path 模板（不暴露高基数 path，如 /api/spot/123）
        # 简单方案：直接用原始 path（项目 path 基数可控）
        path_template = _normalize_path(path)

        start_time = time.perf_counter()
        status_code_holder = {"code": 500}  # 默认 500（异常未捕获时）

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                status_code_holder["code"] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_s = time.perf_counter() - start_time
            status_code = status_code_holder["code"]

            try:
                http_requests_total.labels(
                    method=method, path=path_template, status=str(status_code),
                ).inc()
                http_request_duration_seconds.labels(
                    method=method, path=path_template,
                ).observe(duration_s)
            except Exception as e:
                # metrics 记录失败不影响主流程
                trip_log.warning(
                    "prom_metrics_record_failed",
                    error=str(e),
                    method=method,
                    path=path_template,
                )


def _normalize_path(path: str) -> str:
    """规范化 path 避免高基数（FastAPI 路由参数替换）。

    例：/api/spot/123 → /api/spot/{id}（避免每条 spot 一个 label）

    简化实现：项目里大部分 path 已经带 /api/{resource}/{id} 模式，
    暂时直接返回原 path（项目 path 基数 < 100，可控）。
    未来如需精确归一化，可挂 FastAPI route matcher。
    """
    return path


# ---------------------------------------------------------------------------
# /metrics 端点（独立注册，不走中间件）
# ---------------------------------------------------------------------------

async def metrics_endpoint(request: Request) -> Response:
    """Prometheus 抓取端点（K8s Prometheus 自动配置 scrape）。"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
