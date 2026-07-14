"""性能图表渲染（对应 Node 版 chart-render.ts）

生成 6 张 PNG 图表到 docs/performance-data/charts/
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "performance-data"
CHART_DIR = DATA_DIR / "charts"


def _load(name: str) -> dict:
    path = DATA_DIR / f"{name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def render_all():
    """渲染全部 6 张图表"""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 11, "figure.facecolor": "white",
                         "axes.facecolor": "white", "axes.grid": True,
                         "grid.alpha": 0.3})

    http_data = _load("http-results")
    sse_data = _load("sse-results")
    llm_data = _load("llm-results")
    cache_data = _load("cache-results")
    env_data = _load("env")

    if http_data:
        _render_qps_p99(http_data)
    if sse_data:
        _render_sse_concurrency(sse_data)
    if llm_data:
        _render_llm_tokens(llm_data)
    if cache_data:
        _render_cache_hitrate(cache_data)
    if env_data:
        _render_resources(env_data)

    _render_percentiles_comparison(http_data, llm_data, sse_data)

    print(f"Charts saved to {CHART_DIR}")


def _render_qps_p99(data: dict):
    """图表 1: QPS 与 P99 柱状图（双 Y 轴）"""
    fig, ax1 = plt.subplots(figsize=(8, 4))
    endpoints = list(data.keys() - {"scenario", "env", "config", "notes"})
    if not endpoints:
        return
    names = [e.capitalize() for e in endpoints]
    qps = [data[e].get("effectiveQps", 0) or data[e].get("qps", 0) for e in endpoints]
    p99 = [data[e].get("p99", 0) for e in endpoints]

    x = np.arange(len(endpoints))
    w = 0.35
    bars = ax1.bar(x - w / 2, qps, w, label="Effective QPS", color="#378add", alpha=0.85)
    ax1.set_ylabel("QPS")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names)

    ax2 = ax1.twinx()
    ax2.bar(x + w / 2, p99, w, label="P99 Latency (ms)", color="#d85a30", alpha=0.85)
    ax2.set_ylabel("P99 (ms)")

    fig.legend(loc="upper right", fontsize=10)
    fig.suptitle("HTTP Endpoint Performance")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "qps-p99.png", dpi=150)
    plt.close(fig)


def _render_sse_concurrency(data: dict):
    """图表 2: SSE 并发折线图"""
    results = data.get("results", [])
    if not results:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    concurrency_levels = [r["concurrency"] for r in results]
    p50 = [np.percentile(r.get("streamDurationsMs", [0]), 50) / 1000 for r in results]
    p95 = [np.percentile(r.get("streamDurationsMs", [0]), 95) / 1000 for r in results]
    p99 = [np.percentile(r.get("streamDurationsMs", [0]), 99) / 1000 for r in results]

    ax.plot(concurrency_levels, p50, "o-", label="P50")
    ax.plot(concurrency_levels, p95, "s-", label="P95")
    ax.plot(concurrency_levels, p99, "^-", label="P99")
    ax.set_xlabel("Concurrency")
    ax.set_ylabel("Duration (s)")
    ax.set_title("SSE Stream Duration by Concurrency")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "sse-concurrency.png", dpi=150)
    plt.close(fig)


def _render_llm_tokens(data: dict):
    """图表 3: LLM 各请求耗时柱状图"""
    requests = data.get("requests", [])
    if not requests:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    durations = [r.get("durationMs", 0) / 1000 for r in requests]
    ax.bar(range(len(durations)), durations, color="#7f77dd", alpha=0.85)
    ax.set_xlabel("Request #")
    ax.set_ylabel("Duration (s)")
    ax.set_title("LLM Recommend Request Duration")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "llm-tokens.png", dpi=150)
    plt.close(fig)


def _render_cache_hitrate(data: dict):
    """图表 4: 缓存命中率环形图"""
    hit_rate = data.get("hitRate", 0)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.pie([hit_rate, 1 - hit_rate], labels=["Cached", "Miss"],
           colors=["#639922", "#d3d1c7"], autopct="%1.1f%%",
           startangle=90, wedgeprops={"width": 0.4})
    ax.set_title("LLM Cache Hit Rate")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "cache-hitrate.png", dpi=150)
    plt.close(fig)


def _render_resources(data: dict):
    """图表 5: 系统资源柱状图"""
    fig, ax = plt.subplots(figsize=(6, 3))
    labels = ["CPU Cores", "Total Mem (GB)", "Free Mem (GB)"]
    values = [
        data.get("cpus", 0),
        round(data.get("totalMemMB", 0) / 1024, 1),
        round(data.get("freeMemMB", 0) / 1024, 1),
    ]
    ax.bar(labels, values, color="#888780", alpha=0.85, width=0.5)
    ax.set_title("System Resources")
    for i, v in enumerate(values):
        ax.text(i, v + 0.3, str(v), ha="center", fontsize=11)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "resources.png", dpi=150)
    plt.close(fig)


def _render_percentiles_comparison(http_data: dict, llm_data: dict, sse_data: dict):
    """图表 6: 多场景分位数对比（对数 Y 轴）"""
    fig, ax = plt.subplots(figsize=(8, 4))
    scenarios = []
    p50_vals, p95_vals, p99_vals = [], [], []

    for name, ep in [("Login", "login"), ("History", "history")]:
        d = http_data.get(ep, {})
        if d:
            scenarios.append(name)
            p50_vals.append(d.get("p50", 0))
            p95_vals.append(d.get("p95", 0))
            p99_vals.append(d.get("p99", 0))

    llm_reqs = llm_data.get("requests", [])
    if llm_reqs:
        durations = [r.get("durationMs", 0) for r in llm_reqs]
        scenarios.append("LLM")
        p50_vals.append(np.percentile(durations, 50))
        p95_vals.append(np.percentile(durations, 95))
        p99_vals.append(np.percentile(durations, 99))

    sse_results = sse_data.get("results", [])
    if sse_results:
        for r in sse_results:
            if r.get("concurrency") == 10:
                durs = r.get("streamDurationsMs", [0])
                scenarios.append("SSE(x10)")
                p50_vals.append(np.percentile(durs, 50))
                p95_vals.append(np.percentile(durs, 95))
                p99_vals.append(np.percentile(durs, 99))

    if not scenarios:
        return

    x = np.arange(len(scenarios))
    w = 0.25
    ax.bar(x - w, p50_vals, w, label="P50", color="#378add", alpha=0.85)
    ax.bar(x, p95_vals, w, label="P95", color="#7f77dd", alpha=0.85)
    ax.bar(x + w, p99_vals, w, label="P99", color="#d85a30", alpha=0.85)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("Latency (ms, log)")
    ax.set_title("P50/P95/P99 by Scenario")
    ax.legend()
    fig.tight_layout()
    fig.savefig(CHART_DIR / "p-percentiles.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    render_all()
