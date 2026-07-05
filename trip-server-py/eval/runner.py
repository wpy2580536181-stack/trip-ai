"""
Eval Runner

加载 fixture → 调 Agent → 跑所有 evaluator → 收集结果

阶段：
1) load_fixtures(): 解析所有 YAML
2) run_fixture(): 跑一个 fixture 的所有 evaluator
3) run_all(): 跑全部 fixture
4) summarize(): 生成报告
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Awaitable, Callable

import yaml

from eval.registry import get_evaluator
from eval.types import (
    AgentOutput,
    EvalResult,
    Fixture,
    FixtureExpected,
    FixtureInput,
    FixtureResult,
    GroupStats,
    ReportSummary,
    TokenUsage,
)

logger = logging.getLogger("eval")


# ==================================================================
# 1. Fixture 加载
# ==================================================================


def _find_fixture_files(fixtures_dir: str | Path) -> list[Path]:
    """递归扫描 fixtures_dir 下所有 .yaml/.yml 文件（跳过 .gitkeep）。"""
    fixtures_dir = Path(fixtures_dir)
    if not fixtures_dir.is_dir():
        logger.error("读取 fixtures 目录失败: %s", fixtures_dir)
        return []

    out: list[Path] = []
    for entry in sorted(fixtures_dir.rglob("*")):
        if entry.name == ".gitkeep":
            continue
        if entry.is_file() and entry.suffix in (".yaml", ".yml"):
            out.append(entry)
    return out


def _parse_fixture(data: dict) -> Fixture:
    """将 YAML 解析出的 dict 转换为 Fixture 数据类。"""
    inp_raw = data.get("input", {})
    exp_raw = data.get("expected", {})

    inp = FixtureInput(
        message=inp_raw.get("message", ""),
        preferences=inp_raw.get("preferences", {}),
        history=inp_raw.get("history", []),
    )

    exp = FixtureExpected(
        city=exp_raw.get("city", ""),
        spot_names=exp_raw.get("spot_names", []),
        must_contain_pois=exp_raw.get("must_contain_pois", []),
        must_contain_keywords=exp_raw.get("must_contain_keywords", []),
        must_not_contain_keywords=exp_raw.get("must_not_contain_keywords", []),
        days=exp_raw.get("days", 0),
        json_valid=exp_raw.get("json_valid", False),
        is_recommendation=exp_raw.get("is_recommendation", False),
        is_detail_answer=exp_raw.get("is_detail_answer", False),
        max_activities_per_day=exp_raw.get("max_activities_per_day", 0),
        tool_calls=exp_raw.get("tool_calls", []),
        activities_have_price_field=exp_raw.get("activities_have_price_field", False),
        contains_price_number=exp_raw.get("contains_price_number", False),
        ground_truth=exp_raw.get("ground_truth", ""),
        keyword_match_mode=exp_raw.get("keyword_match_mode", "all"),
    )

    return Fixture(
        id=data.get("id", ""),
        description=data.get("description", ""),
        tags=data.get("tags", []),
        input=inp,
        expected=exp,
        evaluators=data.get("evaluators", []),
    )


def load_fixtures(fixtures_dir: str | Path) -> list[Fixture]:
    """加载 fixtures 目录下的所有 YAML 文件。"""
    files = _find_fixture_files(fixtures_dir)
    fixtures: list[Fixture] = []

    for path in files:
        rel = path.relative_to(fixtures_dir) if isinstance(fixtures_dir, Path) else path
        try:
            content = path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                logger.warning("fixture %s 格式错误（非 dict），跳过", rel)
                continue
            if not parsed.get("id") or not parsed.get("input") or not parsed.get("expected"):
                logger.warning("fixture %s 缺少必要字段（id/input/expected），跳过", rel)
                continue
            fixtures.append(_parse_fixture(parsed))
        except Exception as e:
            logger.error("fixture %s 解析失败: %s", rel, e)

    logger.info("加载了 %d 个 fixture", len(fixtures))
    return fixtures


# ==================================================================
# 2. 跑单个 fixture
# ==================================================================


# Agent 函数类型
MockAgentFn = Callable[[Fixture], AgentOutput]
AsyncAgentFn = Callable[[Fixture], Awaitable[AgentOutput]]
OnAfterFixtureFn = Callable[[Fixture], Awaitable[None] | None]
OnProgressFn = Callable[[FixtureResult], None]


async def run_fixture(
    fixture: Fixture,
    *,
    mock_agent: MockAgentFn | None = None,
    agent_fn: AsyncAgentFn | None = None,
    on_after_fixture: OnAfterFixtureFn | None = None,
    on_progress: OnProgressFn | None = None,
    samples: int = 1,
) -> FixtureResult:
    """跑一个 fixture，支持多采样投票。

    Args:
        fixture: 要跑的 fixture
        mock_agent: 同步 mock agent（测试 evaluator 时用）
        agent_fn: 异步真实 agent
        on_after_fixture: fixture 完成后调用（用来加间隔）
        on_progress: 实时进度回调
        samples: 多采样次数（默认 1，>1 时取多数决定）
    """
    start = time.monotonic()
    samples = max(1, samples)
    evaluator_results: dict[str, EvalResult] = {}
    all_outputs: list[AgentOutput] = []
    last_error: str | None = None

    # 1) 拿 Agent 输出（多采样）
    for s in range(samples):
        output: AgentOutput | None = None
        error: str | None = None

        try:
            if agent_fn is not None:
                output = await agent_fn(fixture)
            elif mock_agent is not None:
                output = mock_agent(fixture)
            else:
                raise RuntimeError("必须提供 mock_agent 或 agent_fn")
        except Exception as e:
            error = str(e)
            logger.error("fixture %s 第 %d 次 Agent 调用失败: %s", fixture.id, s + 1, error)

        if output is not None:
            all_outputs.append(output)
        if error is not None:
            last_error = error

        # 1.5) fixture 完成后钩子（RealAgent 用它做间隔）
        if on_after_fixture is not None:
            try:
                result = on_after_fixture(fixture)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.warning("on_after_fixture 钩子失败: %s", e)

        if samples > 1:
            logger.info("  [%s] sample %d/%d 完成", fixture.id, s + 1, samples)

    main_output = all_outputs[0] if all_outputs else None

    # 2) 跑每个 evaluator
    if samples > 1 and len(all_outputs) > 0:
        # 多采样：每个 evaluator 跑 N 次，取多数决定
        for name in fixture.evaluators:
            evaluator = get_evaluator(name)
            if evaluator is None:
                evaluator_results[name] = EvalResult(
                    passed=False, reason=f'evaluator "{name}" 未注册'
                )
                continue

            per_sample: list[EvalResult] = []
            for o in all_outputs:
                try:
                    per_sample.append(evaluator(o, fixture))
                except Exception as e:
                    per_sample.append(EvalResult(passed=False, reason=f'evaluator "{name}" 抛错: {e}'))

            pass_count = sum(1 for r in per_sample if r.passed)
            majority = pass_count > len(per_sample) / 2
            first_fail_reason = next((r.reason for r in per_sample if not r.passed), "")
            evaluator_results[name] = EvalResult(
                passed=majority,
                reason="" if majority else (first_fail_reason or f"{pass_count}/{len(per_sample)} 样本失败"),
                details={"pass_count": pass_count, "total_samples": len(per_sample), "per_sample": per_sample},
            )
    else:
        # 单采样
        if main_output is not None:
            for name in fixture.evaluators:
                evaluator = get_evaluator(name)
                if evaluator is None:
                    evaluator_results[name] = EvalResult(
                        passed=False, reason=f'evaluator "{name}" 未注册'
                    )
                    continue
                try:
                    evaluator_results[name] = evaluator(main_output, fixture)
                except Exception as e:
                    evaluator_results[name] = EvalResult(
                        passed=False, reason=f'evaluator "{name}" 抛错: {e}'
                    )

    # 3) 整体 pass = 所有 evaluator 都 pass
    passed = all(r.passed for r in evaluator_results.values()) if evaluator_results else False
    duration_ms = int((time.monotonic() - start) * 1000)

    return FixtureResult(
        fixture_id=fixture.id,
        description=fixture.description,
        tags=fixture.tags or [],
        passed=passed,
        agent_output=main_output,
        evaluator_results=evaluator_results,
        duration_ms=duration_ms,
        error=last_error,
    )


# ==================================================================
# 3. 跑全部 fixture
# ==================================================================


async def run_all(
    fixtures: list[Fixture],
    *,
    mock_agent: MockAgentFn | None = None,
    agent_fn: AsyncAgentFn | None = None,
    on_after_fixture: OnAfterFixtureFn | None = None,
    on_progress: OnProgressFn | None = None,
    samples: int = 1,
) -> list[FixtureResult]:
    """跑全部 fixture 并返回结果列表。"""
    results: list[FixtureResult] = []
    for f in fixtures:
        logger.info("[%s] %s", f.id, f.description)
        r = await run_fixture(
            f,
            mock_agent=mock_agent,
            agent_fn=agent_fn,
            on_after_fixture=on_after_fixture,
            on_progress=on_progress,
            samples=samples,
        )
        results.append(r)
        status = "✓" if r.passed else "✗"
        failed_parts = [
            f"{k}: {v.reason}" for k, v in r.evaluator_results.items() if not v.passed
        ]
        failed_str = " | ".join(failed_parts)
        logger.info("  %s %dms%s", status, r.duration_ms, f"  失败: {failed_str}" if failed_str else "")
        if on_progress is not None:
            on_progress(r)
    return results


# ==================================================================
# 4. 报告汇总
# ==================================================================


def summarize(results: list[FixtureResult]) -> ReportSummary:
    """汇总所有 fixture 结果，生成 ReportSummary。"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    total_duration = sum(r.duration_ms for r in results)

    # Token 累计
    tokens_agg = TokenUsage()
    has_tokens = False
    for r in results:
        if r.agent_output and r.agent_output.tokens:
            t = r.agent_output.tokens
            tokens_agg.prompt += t.prompt
            tokens_agg.completion += t.completion
            tokens_agg.total += t.total
            tokens_agg.cached += t.cached
            has_tokens = True

    total_tokens: TokenUsage | None = tokens_agg if has_tokens else None

    # 按 tag
    by_tag: dict[str, GroupStats] = {}
    for r in results:
        tags = r.tags if r.tags else ["(untagged)"]
        for tag in tags:
            if tag not in by_tag:
                by_tag[tag] = GroupStats()
            by_tag[tag].total += 1
            if r.passed:
                by_tag[tag].passed += 1

    # 按 evaluator
    by_evaluator: dict[str, GroupStats] = {}
    for r in results:
        for name, eval_result in r.evaluator_results.items():
            if name not in by_evaluator:
                by_evaluator[name] = GroupStats()
            by_evaluator[name].total += 1
            if eval_result.passed:
                by_evaluator[name].passed += 1

    return ReportSummary(
        total_fixtures=total,
        passed_fixtures=passed,
        failed_fixtures=total - passed,
        total_duration_ms=total_duration,
        pass_rate=passed / total if total > 0 else 0.0,
        by_tag=by_tag,
        by_evaluator=by_evaluator,
        total_tokens=total_tokens,
    )
