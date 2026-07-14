"""
Evaluator 注册表

新增 evaluator 时：
1) 在对应 evaluators/*.py 里实现
2) 用 register_evaluator 装饰器注册
"""

from __future__ import annotations

from typing import Callable

from eval.types import AgentOutput, EvalResult, Fixture

# Evaluator 函数签名：(output: AgentOutput, fixture: Fixture) -> EvalResult
EvaluatorFn = Callable[[AgentOutput, Fixture], EvalResult]

_EVALUATORS: dict[str, EvaluatorFn] = {}


def register_evaluator(name: str) -> Callable[[EvaluatorFn], EvaluatorFn]:
    """Decorator to register an evaluator function.

    Usage:
        @register_evaluator("schema_check")
        def schema_check(output: AgentOutput, fixture: Fixture) -> EvalResult:
            ...
    """
    def decorator(fn: EvaluatorFn) -> EvaluatorFn:
        _EVALUATORS[name] = fn
        return fn
    return decorator


def get_evaluator(name: str) -> EvaluatorFn | None:
    """Return the registered evaluator with the given name, or None."""
    return _EVALUATORS.get(name)


def list_evaluators() -> list[str]:
    """Return all registered evaluator names."""
    return list(_EVALUATORS.keys())
