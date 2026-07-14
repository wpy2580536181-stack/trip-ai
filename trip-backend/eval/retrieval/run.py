"""
检索层评估 CLI。

两种模式：
  - mock（默认）：使用简单关键词匹配模拟检索，验证指标计算流水线
  - real：连接真实后端，调用 search_spots() 执行实际检索

用法：
  uv run python -m eval.retrieval.run
  uv run python -m eval.retrieval.run --mode mock --k 1 3 5 10 20
  uv run python -m eval.retrieval.run --mode real --base-url http://localhost:8000
  uv run python -m eval.retrieval.run --save
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional

from eval.retrieval.dataset import (
    SPOTS,
    QUERIES,
    RetrievalTestCase,
    Spot,
    build_spot_id_to_name,
    get_spots_by_id,
    dataset_summary,
)
from eval.retrieval.metrics import (
    RetrievalReport,
    QueryResult,
    evaluate_retrieval,
    find_rank,
    calc_hit_at_k,
    calc_mrr_for_query,
)

logger = logging.getLogger(__name__)

TZ = timezone(timedelta(hours=8))

# ──────────────────────────────────────────────
# Mock 检索器：基于关键词匹配的简单模拟
# ──────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """简单中文分词（按字和二元组）+ 英文单词拆分"""
    text = text.lower()
    # 提取中文单字
    chars = set(re.findall(r"[\u4e00-\u9fff]", text))
    # 提取中文二元组（两个连续的中文字）
    bigrams = set()
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for i in range(len(chinese_chars) - 1):
        bigrams.add(chinese_chars[i] + chinese_chars[i + 1])
    # 提取英文单词
    words = set(re.findall(r"[a-z]+", text))
    return chars | bigrams | words


def _spot_to_text(spot: Spot) -> str:
    """将景点转为可匹配的文本"""
    parts = [spot.name, spot.city, spot.category, spot.description] + spot.tags
    return " ".join(parts)


def _jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Jaccard 相似度"""
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def mock_search(query: str, top_k: int = 20) -> list[int]:
    """模拟检索：基于关键词的 Jaccard 相似度排序。

    用三元组匹配和城市/类别加权，近似模拟真实检索引擎的行为。
    """
    query_tokens = _tokenize(query)
    # 检测 query 中是否包含城市名
    query_cities = set()
    for s in SPOTS:
        if s.city in query:
            query_cities.add(s.city)

    # 检测 query 中是否包含类别名
    query_categories = set()
    for s in SPOTS:
        if s.category in query:
            query_categories.add(s.category)

    scored: list[tuple[int, float]] = []
    for spot in SPOTS:
        spot_text = _spot_to_text(spot)
        spot_tokens = _tokenize(spot_text)
        sim = _jaccard_similarity(query_tokens, spot_tokens)

        # 城市加权：如果 query 中提到城市且匹配，加分
        if spot.city in query_cities:
            sim += 0.2

        # 类别加权
        if spot.category in query_categories:
            sim += 0.1

        # 名称直接匹配加权
        if spot.name in query or any(c in spot.name for c in query if len(c) >= 2):
            sim += 0.15

        # 高评分加权
        if spot.rating >= 4.5:
            sim += 0.05

        scored.append((spot.id, sim))

    # 按分数降序排列
    scored.sort(key=lambda x: x[1], reverse=True)
    return [sid for sid, _ in scored[:top_k]]


# ──────────────────────────────────────────────
# Real 检索器：连接真实后端
# ──────────────────────────────────────────────


class RealRetriever:
    """连接真实 Python 后端的检索器。"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._httpx = None

    async def _get_client(self):
        if self._httpx is None:
            import httpx
            self._httpx = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        return self._httpx

    async def search(self, query: str, top_k: int = 20, city: Optional[str] = None) -> list[int]:
        """调用后端 search_spots API 进行检索并返回排名 ID 列表。"""
        import httpx

        client = await self._get_client()
        params = {"q": query, "limit": top_k}
        if city:
            params["city"] = city

        try:
            resp = await client.get("/api/knowledge/spots/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            # 后端返回格式: {code: 200, data: {items: [{id, name, ...}]}}
            if isinstance(data, dict):
                items = data.get("data", {}).get("items", data.get("items", []))
            else:
                items = data
            return [item["id"] for item in items if "id" in item]
        except httpx.HTTPError as e:
            logger.warning(f"Real search failed for '{query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error for '{query}': {e}")
            return []

    async def close(self):
        if self._httpx:
            await self._httpx.aclose()


# ──────────────────────────────────────────────
# 评估运行器
# ──────────────────────────────────────────────


def run_mock_eval() -> RetrievalReport:
    """使用 Mock 检索器运行评估"""
    logger.info("Running retrieval evaluation (mock mode)...")
    spot_id_to_name = build_spot_id_to_name()
    query_ids = [q.gold_spot_id for q in QUERIES]
    ranked_lists = [mock_search(q.query) for q in QUERIES]

    report = evaluate_retrieval(query_ids, ranked_lists, spot_id_to_name)
    report.title = "RAG Retrieval Evaluation Report (mock mode)"

    # 补充 query 级元数据
    for i, qr in enumerate(report.per_query):
        t = QUERIES[i]
        qr.query = t.query
        qr.gold_city = t.gold_city

    report.timestamp = datetime.now(TZ).isoformat()
    return report


async def run_real_eval(base_url: str) -> RetrievalReport:
    """使用真实后端运行评估"""
    logger.info(f"Running retrieval evaluation (real mode, backend={base_url})...")
    spot_id_to_name = build_spot_id_to_name()
    retriever = RealRetriever(base_url)

    query_ids = [q.gold_spot_id for q in QUERIES]
    ranked_lists: list[list[int]] = []

    total = len(QUERIES)
    for i, q in enumerate(QUERIES):
        logger.info(f"[{i+1}/{total}] Searching: '{q.query}' → expecting {q.gold_spot_name}")
        results = await retriever.search(q.query, city=q.gold_city)
        ranked_lists.append(results)

    await retriever.close()

    report = evaluate_retrieval(query_ids, ranked_lists, spot_id_to_name)
    report.title = "RAG Retrieval Evaluation Report (real mode)"

    for i, qr in enumerate(report.per_query):
        t = QUERIES[i]
        qr.query = t.query
        qr.gold_city = t.gold_city

    report.timestamp = datetime.now(TZ).isoformat()
    return report


# ──────────────────────────────────────────────
# 报告输出
# ──────────────────────────────────────────────


def print_report(report: RetrievalReport):
    """控制台输出评估报告"""
    sep = "=" * 72
    dash = "-" * 72

    print(f"\n{sep}")
    print(f"  {report.title}")
    print(f"  {report.timestamp}")
    print(f"{sep}")

    # 数据集概览
    ds = dataset_summary()
    print(f"\n📊 数据集: {ds['total_spots']} 景点 × {ds['total_queries']} query")
    print(f"  城市分布: {ds['cities']}")
    print(f"  类别分布: {ds['categories']}")
    print(f"  Query 类型: {ds['query_types']}")

    # 聚合指标
    print(f"\n📈 聚合指标:")
    print(f"  {'K':>5} | {'Hit Rate':>10}")
    print(f"  {dash}")
    for k in report.k_values:
        hr = report.hit_rates.get(k, 0)
        bar = "█" * int(hr * 40) + "░" * (40 - int(hr * 40))
        print(f"  {k:>5} | {hr:>8.1%}  {bar}")
    print(f"  {'MRR':>5} | {report.mrr:>8.4f}")

    # 异常 query
    if report.worst_queries:
        print(f"\n⚠️ Top-5 未命中 query ({len(report.worst_queries)} 条):")
        for w in report.worst_queries[:5]:
            tid = w["index"]
            q = QUERIES[tid]
            print(f"  [{q.query_type}] \"{q.query}\" → 期望 \"{q.gold_spot_name}\" (rank={w['rank']})")

    # 优化建议
    print(f"\n💡 优化建议:")
    for rec in report.recommendations:
        print(f"  • {rec}")

    print(f"\n{sep}\n")


def save_report(report: RetrievalReport, output_dir: str = "eval-reports"):
    """保存评估报告为 JSON"""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now(TZ).strftime("%Y-%m-%d_%H-%M-%S")
    mode = "mock" if "mock" in report.title.lower() else "real"
    filename = f"{timestamp}_retrieval_{mode}.json"
    filepath = os.path.join(output_dir, filename)

    data = {
        "title": report.title,
        "timestamp": report.timestamp,
        "dataset_size": report.dataset_size,
        "k_values": report.k_values,
        "hit_rates": {f"k{k}": v for k, v in report.hit_rates.items()},
        "mrr": report.mrr,
        "by_city": report.by_city,
        "by_category": report.by_category,
        "by_query_type": report.by_query_type,
        "worst_queries": report.worst_queries,
        "recommendations": report.recommendations,
        "per_query": [
            {
                "query": qr.query,
                "gold_spot_name": qr.gold_spot_name,
                "gold_city": qr.gold_city,
                "rank": qr.rank,
                "normalized_rank": qr.normalized_rank,
                "hit_at_k": qr.hit_at_k,
                "retrieved_at_top": qr.retrieved_names[:10],
            }
            for qr in report.per_query
        ],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Report saved: {filepath}")
    return filepath


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAG Retrieval Evaluation (Hit@K + MRR)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python -m eval.retrieval.run                          # mock 模式
  uv run python -m eval.retrieval.run --mode real --base-url http://localhost:8000
  uv run python -m eval.retrieval.run --save                    # 保存报告
  uv run python -m eval.retrieval.run --k 1 3 5 10              # 自定义 K 值
  uv run python -m eval.retrieval.run --verbose                 # 详细日志
        """,
    )
    parser.add_argument(
        "--mode", choices=["mock", "real"], default="mock",
        help="评估模式（默认 mock）",
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000",
        help="后端地址（real 模式用，默认 http://localhost:8000）",
    )
    parser.add_argument(
        "--k", type=int, nargs="+", default=[1, 3, 5, 10, 20],
        help="要计算的 K 值列表（默认 1 3 5 10 20）",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="保存报告到 eval-reports/ 目录",
    )
    parser.add_argument(
        "--output-dir", default="eval-reports",
        help="报告输出目录（默认 eval-reports）",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="输出详细调试日志",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None):
    args = parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    start = time.time()

    if args.mode == "mock":
        report = run_mock_eval()
    else:
        import asyncio
        report = asyncio.run(run_real_eval(args.base_url))

    # 覆盖 K 值（如果不一致）
    if args.k != [1, 3, 5, 10, 20]:
        report.k_values = args.k
        # 重算 hit_rates
        n = report.dataset_size
        report.hit_rates = {}
        for k in args.k:
            hits = sum(1 for qr in report.per_query if qr.hit_at_k.get(k, False))
            report.hit_rates[k] = round(hits / n, 4) if n > 0 else 0.0

    elapsed = time.time() - start
    report.timestamp = datetime.now(TZ).isoformat()

    print_report(report)

    if args.save:
        path = save_report(report, args.output_dir)
        print(f"Report saved to: {path}")

    print(f"Done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
