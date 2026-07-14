#!/usr/bin/env python3
"""
Eval CLI 入口

用法：
    python -m eval.run                          # mock 模式
    python -m eval.run --real                   # 真实 agent
    python -m eval.run --real --id 001          # 跑指定 fixture
    python -m eval.run --real --tag multi-turn  # 跑指定 tag
    python -m eval.run --samples 3              # 多采样投票

真实模式环境变量：
    EVAL_BASE_URL       默认 http://127.0.0.1:8000
    EVAL_USERNAME       默认 eval-test
    EVAL_PASSWORD       默认 EvalTest@2026
    EVAL_TIMEOUT_MS     默认 90000
    EVAL_DELAY_MS       默认 2000
    EVAL_DEBUG=1        打印原始 agent 输出

退出码：
    0 = 全部通过
    1 = 有失败
    2 = runner 自身错误
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# 让 `python -m eval.run` 能找到 eval 包
# 将项目根目录添加到 sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import eval.evaluators  # noqa: F401  触发 @register_evaluator 装饰器
from eval.mock_agent import mock_agent
from eval.real_agent import RealAgent, RealAgentOptions
from eval.registry import list_evaluators
from eval.runner import load_fixtures, run_all, summarize
from eval.types import Fixture, FixtureResult, ReportSummary

# ---------------------------------------------------------------------------
# 彩色输出辅助（无依赖 fallback）
# ---------------------------------------------------------------------------

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _GREEN = Fore.GREEN
    _RED = Fore.RED
    _YELLOW = Fore.YELLOW
    _CYAN = Fore.CYAN
    _GRAY = Fore.LIGHTBLACK_EX
    _BOLD = Style.BRIGHT
    _RESET = Style.RESET_ALL
except ImportError:
    _GREEN = _RED = _YELLOW = _CYAN = _GRAY = _BOLD = _RESET = ""


def _color_pass_rate(rate: float) -> str:
    if rate == 1.0:
        return _GREEN
    elif rate >= 0.8:
        return _YELLOW
    return _RED


# ---------------------------------------------------------------------------
# CLI 参数解析
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.run",
        description="Trip Agent Eval Runner",
    )
    p.add_argument("--real", action="store_true", help="Run against real agent (requires backend)")
    p.add_argument("--id", dest="ids", action="append", default=[], help="Run specific fixture(s)")
    p.add_argument("--tag", dest="tags", action="append", default=[], help="Run fixtures with tag(s)")
    p.add_argument("--samples", type=int, default=1, help="Samples per fixture, majority vote (default 1)")
    p.add_argument("--save", action="store_true", help="Save report to eval-reports/")
    p.add_argument("--debug", action="store_true", help="Print raw agent output")
    return p


def filter_fixtures(fixtures: list[Fixture], ids: list[str], tags: list[str]) -> list[Fixture]:
    filtered = []
    for f in fixtures:
        if ids and f.id not in ids:
            continue
        if tags and not any(t in (f.tags or []) for t in tags):
            continue
        filtered.append(f)
    return filtered


# ---------------------------------------------------------------------------
# 结果打印
# ---------------------------------------------------------------------------


def print_debug(results: list[FixtureResult]) -> None:
    print(f"\n{_BOLD}=== DEBUG: 原始 Agent 输出 ==={_RESET}\n")
    for r in results:
        print(f"{_BOLD}[{r.fixture_id}]{_RESET}")
        if r.agent_output:
            if r.agent_output.text:
                print(f"{_GRAY}--- text 前 500 字 ---{_RESET}")
                print(r.agent_output.text[:500])
                print(f"{_GRAY}--- text 后 500 字 ---{_RESET}")
                print(r.agent_output.text[-500:])
            if r.agent_output.json:
                print(f"{_GRAY}--- json ---{_RESET}")
                print(json.dumps(r.agent_output.json, ensure_ascii=False, indent=2)[:800])
            if r.agent_output.tool_calls:
                print(f"{_GRAY}--- tool_calls ---{_RESET}")
                print(json.dumps([tc.__dict__ for tc in r.agent_output.tool_calls], ensure_ascii=False, indent=2))
            if r.agent_output.error:
                print(f"{_RED}--- error ---{_RESET}")
                print(r.agent_output.error)
        print()


def print_results(results: list[FixtureResult]) -> None:
    print(f"\n{_BOLD}=== 详细结果 ==={_RESET}\n")
    for r in results:
        status = f"{_GREEN}✓ PASS{_RESET}" if r.passed else f"{_RED}✗ FAIL{_RESET}"
        print(f"{status}  {_BOLD}{r.fixture_id}{_RESET}  {_GRAY}{r.description}{_RESET}")
        if r.error:
            print(f"        {_RED}fixture 错误: {r.error}{_RESET}")
        for name, ev in r.evaluator_results.items():
            sym = f"{_GREEN}  ✓{_RESET}" if ev.passed else f"{_RED}  ✗{_RESET}"
            reason = f"{_RED} — {ev.reason}{_RESET}" if ev.reason else ""
            print(f"        {sym} {_GRAY}{name}{_RESET}{reason}")


def print_summary(summary: ReportSummary, real_mode: bool, samples: int) -> None:
    print(f"\n{_BOLD}=== 汇总 ==={_RESET}\n")
    pct = f"{summary.pass_rate * 100:.1f}"
    color = _color_pass_rate(summary.pass_rate)
    print(f"{color}{summary.passed_fixtures}/{summary.total_fixtures} 通过{_RESET} ({pct}%)  {_GRAY}{summary.total_duration_ms}ms{_RESET}")

    if summary.total_tokens:
        t = summary.total_tokens
        hit_rate = t.cached / t.prompt if t.prompt > 0 else 0.0
        hit_pct = f"{hit_rate * 100:.1f}"
        hit_color = _color_pass_rate(hit_rate)
        print(f"{_GRAY}  Token: prompt={t.prompt:,}  completion={t.completion:,}  total={t.total:,}{_RESET}")
        print(f"  Cache: cached={t.cached:,}  {hit_color}hitRate={hit_pct}%{_RESET}")

    if summary.by_tag:
        print(f"\n{_BOLD}按 tag:{_RESET}")
        for tag, s in summary.by_tag.items():
            t_str = f"{s.passed}/{s.total}"
            c = _color_pass_rate(s.pass_rate)
            print(f"  {c}{t_str:<7}{_RESET}  {tag}")

    if summary.by_evaluator:
        print(f"\n{_BOLD}按 evaluator:{_RESET}")
        for name, s in summary.by_evaluator.items():
            t_str = f"{s.passed}/{s.total}"
            c = _color_pass_rate(s.pass_rate)
            print(f"  {c}{t_str:<7}{_RESET}  {name}")


def save_report(
    summary: ReportSummary,
    results: list[FixtureResult],
    real_mode: bool,
    samples: int,
) -> None:
    reports_dir = Path(__file__).resolve().parent.parent / "eval-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    mode = "real" if real_mode else "mock"
    filename = f"{date_str}_{time_str}_{mode}_s{samples}.json"
    filepath = reports_dir / filename

    report = {
        "timestamp": now.isoformat(),
        "mode": mode,
        "samples": samples,
        "summary": {
            "total_fixtures": summary.total_fixtures,
            "passed_fixtures": summary.passed_fixtures,
            "failed_fixtures": summary.failed_fixtures,
            "pass_rate": summary.pass_rate,
            "total_duration_ms": summary.total_duration_ms,
            "by_tag": {k: {"passed": v.passed, "total": v.total, "pass_rate": v.pass_rate} for k, v in summary.by_tag.items()},
            "by_evaluator": {k: {"passed": v.passed, "total": v.total, "pass_rate": v.pass_rate} for k, v in summary.by_evaluator.items()},
            "total_tokens": summary.total_tokens.__dict__ if summary.total_tokens else None,
        },
        "fixtures": [
            {
                "id": r.fixture_id,
                "description": r.description,
                "tags": r.tags,
                "pass": r.passed,
                "duration_ms": r.duration_ms,
                "error": r.error,
                "evaluators": {k: {"pass": v.passed, "reason": v.reason} for k, v in r.evaluator_results.items()},
            }
            for r in results
        ],
    }
    filepath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{_GRAY}报告已保存: eval-reports/{filename}{_RESET}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def async_main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    real_mode: bool = args.real
    ids: list[str] = args.ids
    tags: list[str] = args.tags
    samples: int = max(1, args.samples)
    save: bool = args.save or os.environ.get("EVAL_SAVE") == "1"
    debug: bool = args.debug or os.environ.get("EVAL_DEBUG") == "1"

    # 配置 logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
    )

    evaluators = list_evaluators()
    print(f"\n{_BOLD}{_CYAN}=== Trip Agent Eval ==={_RESET}\n")
    print(f"{_GRAY}fixtures: {FIXTURES_DIR}{_RESET}")
    print(f"{_GRAY}mode: {'REAL agent' if real_mode else 'MOCK agent'}{_RESET}")
    print(f"{_GRAY}samples: {samples} ({'majority vote' if samples > 1 else 'single'}){_RESET}")
    print(f"{_GRAY}registered evaluators: {len(evaluators)} ({', '.join(evaluators)}){_RESET}\n")

    # 加载 fixtures
    try:
        fixtures = load_fixtures(FIXTURES_DIR)
    except Exception as e:
        print(f"{_RED}加载 fixture 失败: {e}{_RESET}", file=sys.stderr)
        return 2

    filtered = filter_fixtures(fixtures, ids, tags)
    if not filtered:
        print(f"{_YELLOW}没有匹配的 fixture{_RESET}", file=sys.stderr)
        return 2
    print(f"{_GRAY}将跑 {len(filtered)}/{len(fixtures)} 个 fixture{_RESET}\n")

    # 构建 agent
    real_agent: RealAgent | None = None
    agent_fn = None
    mock_agent_fn = None

    if real_mode:
        base_url = os.environ.get("EVAL_BASE_URL", "http://127.0.0.1:8000")
        username = os.environ.get("EVAL_USERNAME", "eval-test")
        password = os.environ.get("EVAL_PASSWORD", "EvalTest@2026")
        timeout_ms = int(os.environ.get("EVAL_TIMEOUT_MS", "90000"))
        delay_ms = int(os.environ.get("EVAL_DELAY_MS", "2000"))

        print(f"{_GRAY}  baseUrl: {base_url}{_RESET}")
        print(f"{_GRAY}  username: {username}{_RESET}")
        print(f"{_GRAY}  timeoutMs: {timeout_ms}{_RESET}")
        print(f"{_GRAY}  delayBetweenMs: {delay_ms}{_RESET}")

        opts = RealAgentOptions(
            base_url=base_url,
            username=username,
            password=password,
            timeout_ms=timeout_ms,
            delay_between_ms=delay_ms,
        )
        real_agent = RealAgent(options=opts)
        agent_fn = real_agent.run
    else:
        mock_agent_fn = mock_agent

    # Progress log
    progress_log = os.environ.get("EVAL_PROGRESS_LOG")

    def _log_progress(msg: str) -> None:
        if progress_log:
            try:
                with open(progress_log, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception:
                pass

    _log_progress(
        f"start {datetime.now(timezone.utc).isoformat()} mode={'real' if real_mode else 'mock'} samples={samples} n={len(filtered)}"
    )

    def on_progress(r: FixtureResult) -> None:
        if real_mode and r.agent_output and r.agent_output.tokens:
            tok = r.agent_output.tokens
            cached = tok.cached
            prompt = tok.prompt
            rate = f"{cached / prompt * 100:.1f}" if prompt > 0 else "0.0"
            _log_progress(
                f"done {r.fixture_id} pass={r.passed} dur={r.duration_ms}ms prompt={prompt} cached={cached} hitRate={rate}%"
            )

    try:
        results = await run_all(
            filtered,
            mock_agent=mock_agent_fn,
            agent_fn=agent_fn,
            on_after_fixture=(lambda f: real_agent.delay()) if real_agent else None,
            on_progress=on_progress if real_mode else None,
            samples=samples,
        )
    except Exception as e:
        print(f"{_RED}runner 出错: {e}{_RESET}", file=sys.stderr)
        return 2
    finally:
        if real_agent:
            await real_agent.close()

    _log_progress(f"end {datetime.now(timezone.utc).isoformat()}")

    # Debug
    if debug:
        print_debug(results)

    # 汇总
    summary = summarize(results)
    print_results(results)
    print_summary(summary, real_mode, samples)

    if save:
        save_report(summary, results, real_mode, samples)

    print()
    return 0 if summary.failed_fixtures == 0 else 1


def main() -> None:
    exit_code = asyncio.run(async_main())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
