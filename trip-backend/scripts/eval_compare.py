"""Eval 报告对比脚本 — 检查通过率是否退化

用法:
    uv run python scripts/eval_compare.py                                     # 使用默认路径 + 80% 阈值
    uv run python scripts/eval_compare.py --current path/to/latest.json       # 指定当前报告
    uv run python scripts/eval_compare.py --baseline path/to/baseline.json    # 指定基线
    uv run python scripts/eval_compare.py --threshold 0.8                     # 自定义阈值
    uv run python scripts/eval_compare.py --output path/to/comparison.json    # 输出路径
    uv run python scripts/eval_compare.py --update-baseline                   # 同时更新基线（CI main 分支用）

退出码:
    0 = 全部通过（通过率 >= 阈值）
    1 = 退化（通过率 < 阈值）
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_DIR / "eval-reports"
DEFAULT_BASELINE = DEFAULT_REPORTS_DIR / "baseline.json"


def find_latest_report(reports_dir: Path) -> Path:
    """在 eval-reports/ 中按文件名时间戳找最新的报告"""
    if not reports_dir.exists():
        raise FileNotFoundError(f"Reports directory not found: {reports_dir}")
    json_files = sorted(reports_dir.glob("*.json"), reverse=True)
    # 排除 baseline.json 和 comparison.json
    candidates = [f for f in json_files if f.name not in ("baseline.json", "comparison.json")]
    if not candidates:
        raise FileNotFoundError(f"No eval reports found in {reports_dir}")
    return candidates[0]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compare(current: dict, baseline: dict, threshold: float) -> dict:
    """对比当前报告与基线，输出差异"""
    # 当前摘要
    cur_summary = current.get("summary", {})
    base_summary = baseline.get("summary", {})

    # Evaluator 级别对比
    cur_by_eval = cur_summary.get("by_evaluator", {})
    base_by_eval = base_summary.get("by_evaluator", {})

    diffs = []
    for name, cur_stat in sorted(cur_by_eval.items()):
        cur_rate = cur_stat.get("pass_rate", 0)
        base_rate = base_by_eval.get(name, {}).get("pass_rate", 0)
        change = round((cur_rate - base_rate) * 100, 1)
        diffs.append({
            "name": name,
            "previous": round(base_rate * 100, 1),
            "current": round(cur_rate * 100, 1),
            "change": change,
            "passed": cur_stat.get("passed", 0),
            "total": cur_stat.get("total", 0),
        })

    # Tag 级别对比
    cur_by_tag = cur_summary.get("by_tag", {})
    base_by_tag = base_summary.get("by_tag", {})
    tag_diffs = []
    for name, cur_stat in sorted(cur_by_tag.items()):
        cur_rate = cur_stat.get("pass_rate", 0)
        base_rate = base_by_tag.get(name, {}).get("pass_rate", 0)
        change = round((cur_rate - base_rate) * 100, 1)
        tag_diffs.append({
            "tag": name,
            "previous": round(base_rate * 100, 1),
            "current": round(cur_rate * 100, 1),
            "change": change,
        })

    # 总体通过率
    overall_rate = cur_summary.get("pass_rate", 0)
    overall_base = base_summary.get("pass_rate", 0)
    passed = overall_rate >= threshold

    # Token 统计
    tokens = cur_summary.get("total_tokens")

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_report": current.get("timestamp", ""),
        "mode": current.get("mode", "unknown"),
        "overallPassRate": round(overall_rate * 100, 1),
        "overallBaseline": round(overall_base * 100, 1),
        "threshold": round(threshold * 100, 1),
        "passed": passed,
        "totalFixtures": cur_summary.get("total_fixtures", 0),
        "passedFixtures": cur_summary.get("passed_fixtures", 0),
        "failedFixtures": cur_summary.get("failed_fixtures", 0),
        "totalDurationMs": cur_summary.get("total_duration_ms", 0),
        "tokens": {
            "prompt": tokens.get("prompt", 0) if tokens else 0,
            "completion": tokens.get("completion", 0) if tokens else 0,
            "total": tokens.get("total", 0) if tokens else 0,
        } if tokens else None,
        "diffs": diffs,
        "tagDiffs": tag_diffs,
    }

    return result


def print_report(result: dict):
    """打印人类可读的对比报告"""
    mode = result["mode"]
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"\n{'='*60}")
    print(f"  Eval Report Comparison ({mode})")
    print(f"{'='*60}")
    print(f"  Status:     {status}")
    print(f"  Pass Rate:  {result['overallPassRate']}%  (threshold: {result['threshold']}%)")
    print(f"  Baseline:   {result['overallBaseline']}%")
    print(f"  Fixtures:   {result['passedFixtures']}/{result['totalFixtures']} passed")
    print(f"  Duration:   {result['totalDurationMs']}ms")
    if result.get("tokens"):
        t = result["tokens"]
        print(f"  Tokens:     prompt={t['prompt']:,}  completion={t['completion']:,}  total={t['total']:,}")

    if result["diffs"]:
        print(f"\n  {'Evaluator':<25} {'Previous':>8} {'Current':>8} {'Change':>8}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
        for d in result["diffs"]:
            change_str = f"+{d['change']}%" if d['change'] > 0 else f"{d['change']}%"
            print(f"  {d['name']:<25} {d['previous']:>7.1f}% {d['current']:>7.1f}% {change_str:>8}")

    if result["tagDiffs"]:
        print(f"\n  {'Tag':<25} {'Previous':>8} {'Current':>8} {'Change':>8}")
        print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
        for d in result["tagDiffs"]:
            change_str = f"+{d['change']}%" if d['change'] > 0 else f"{d['change']}%"
            print(f"  {d['tag']:<25} {d['previous']:>7.1f}% {d['current']:>7.1f}% {change_str:>8}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Eval report comparison tool")
    parser.add_argument("--current", help="Current report path (default: latest in eval-reports/)")
    parser.add_argument("--baseline", help=f"Baseline path (default: {DEFAULT_BASELINE})")
    parser.add_argument("--threshold", type=float, default=0.8, help="Pass rate threshold (default: 0.8)")
    parser.add_argument("--output", help="Output path for comparison JSON (default: eval-reports/comparison.json)")
    parser.add_argument("--update-baseline", action="store_true", help="Update baseline to current report")
    args = parser.parse_args()

    # 确定路径
    current_path = Path(args.current) if args.current else find_latest_report(DEFAULT_REPORTS_DIR)
    baseline_path = Path(args.baseline) if args.baseline else DEFAULT_BASELINE
    output_path = Path(args.output) if args.output else (DEFAULT_REPORTS_DIR / "comparison.json")

    # 加载
    current = load_json(current_path)
    baseline = load_json(baseline_path)

    if not current:
        print(f"Error: Current report not found or empty: {current_path}", file=sys.stderr)
        sys.exit(2)

    print(f"Current:  {current_path.name}")
    print(f"Baseline: {baseline_path.name if baseline_path.exists() else '(none)'}")
    print(f"Threshold: {args.threshold * 100:.0f}%")

    # 对比
    result = compare(current, baseline, args.threshold)
    print_report(result)

    # 输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Comparison saved: {output_path}")

    # 更新基线（--update-baseline 模式）
    if args.update_baseline:
        baseline_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Baseline updated: {baseline_path}")

    # 退出码
    if not result["passed"]:
        print(f"FAIL: Pass rate {result['overallPassRate']}% < threshold {result['threshold']}%")
        sys.exit(1)

    print(f"PASS: Pass rate {result['overallPassRate']}% >= threshold {result['threshold']}%")
    sys.exit(0)


if __name__ == "__main__":
    main()
