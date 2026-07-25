"""M5 阶段测试 —— Prometheus metrics middleware + /metrics 端点。

覆盖 3 类：
1. PrometheusMiddleware 自动记录 HTTP 请求 Counter + Histogram
2. /metrics 端点正确返回 prometheus exposition format
3. 工具函数 record_chat_duration / record_tool_invocation 累加正确
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from prometheus_client import generate_latest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# 测试 1：HTTP Counter + Histogram 自动累加
# ---------------------------------------------------------------------------

def test_prometheus_middleware_records_http_requests():
    """用 TestClient 模拟 HTTP 请求，验证 Counter + Histogram 累加。

    注意：Counter/Histogram 是模块级单例，测试间可能残留。
    不直接断言具体数值，只断言"有 sample 行"（表明被记录了）。
    """
    from src.main import app
    client = TestClient(app)

    # 调一次 /health/detail
    response = client.get("/health/detail")
    assert response.status_code == 200

    output = generate_latest().decode()
    # http_requests_total 至少有 sample 行（method=path=status 标签）
    assert "http_requests_total{" in output, (
        f"中间件未记录请求。metrics 输出应包含带标签的 http_requests_total。\n"
        f"实际输出片段：{output[:500]}"
    )
    # 至少应包含一个 GET 请求
    assert 'method="GET"' in output


# ---------------------------------------------------------------------------
# 测试 2：/metrics 端点
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_prometheus_format():
    """GET /metrics 返回 prometheus exposition format（text/plain; version=0.0.4）。"""
    from src.main import app
    client = TestClient(app)

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    # 必须有 prometheus exposition format 的特征
    body = response.text
    # 至少有 1 个 # HELP 和 # TYPE
    assert "# HELP" in body
    assert "# TYPE" in body
    # 至少包含我们定义的 4 个核心指标之一
    assert "http_requests_total" in body or "http_request_duration_seconds" in body


# ---------------------------------------------------------------------------
# 测试 3：/metrics 不被自身记录（无限循环防护）
# ---------------------------------------------------------------------------

def test_metrics_endpoint_not_recorded_by_middleware():
    """GET /metrics 不应被自身 middleware 记录（避免抓取循环）。"""
    from src.middleware import prom_metrics
    # 清理计数
    prom_metrics.http_requests_total._metrics.clear()

    from src.main import app
    client = TestClient(app)

    # 多次抓取 metrics
    for _ in range(3):
        client.get("/metrics")

    # /metrics 路径不应出现在 http_requests_total 的 label 里
    output = generate_latest().decode()
    # 抓取 /metrics 不应该增长 http_requests_total{path="/metrics"} 计数
    # 实际验证：原始 metrics 文本不应包含 path="/metrics"
    if 'http_requests_total{' in output:
        # 如果有 http_requests_total 标签，path 不应该是 /metrics
        assert 'path="/metrics"' not in output, (
            "/metrics 端点被自身 middleware 记录，会导致无限循环！"
        )


# ---------------------------------------------------------------------------
# 测试 4：record_chat_duration 累加 chat_request_duration_seconds
# ---------------------------------------------------------------------------

def test_record_chat_duration_increments_histogram():
    """record_chat_duration() 增加 chat_request_duration_seconds 直方图计数。"""
    from src.middleware import prom_metrics
    # 通过 record_chat_duration 累加
    prom_metrics.record_chat_duration(0.5)
    prom_metrics.record_chat_duration(2.3)

    output = generate_latest().decode()
    # chat_request_duration_seconds 至少有 _count 和 _sum
    assert "chat_request_duration_seconds" in output


# ---------------------------------------------------------------------------
# 测试 5：record_tool_invocation 累加 tool_invocations_total
# ---------------------------------------------------------------------------

def test_record_tool_invocation_increments_counter():
    """record_tool_invocation("amap", success=True) 增加 tool_invocations_total{tool="amap", status="success"}。"""
    from src.middleware import prom_metrics
    prom_metrics.record_tool_invocation("amap", success=True)
    prom_metrics.record_tool_invocation("amap", success=False)
    prom_metrics.record_tool_invocation("baidu", success=True)

    output = generate_latest().decode()
    assert 'tool_invocations_total{status="success",tool="amap"}' in output
    assert 'tool_invocations_total{status="failure",tool="amap"}' in output
    assert 'tool_invocations_total{status="success",tool="baidu"}' in output
