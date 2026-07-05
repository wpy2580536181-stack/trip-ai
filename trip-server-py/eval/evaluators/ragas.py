"""
RAGAs 评估器 —— 生成层质量评估。

实现四个核心指标：
  - Faithfulness（忠实度）：答案是否有幻觉
  - Answer Relevancy（答案相关性）：答案是否答非所问
  - Context Recall（上下文召回率）：检索覆盖是否足够
  - Context Precision（上下文精确率）：检索排序质量

集成到现有 eval 框架，作为一个 evaluator 注册。
"""

import logging
from typing import Optional

from eval.types import AgentOutput, EvalResult, Fixture, ToolCall
from eval.registry import register_evaluator

logger = logging.getLogger(__name__)

# 指标阈值
THRESHOLD_FAITHFULNESS = 0.7
THRESHOLD_ANSWER_RELEVANCY = 0.7
THRESHOLD_CONTEXT_RECALL = 0.6
THRESHOLD_CONTEXT_PRECISION = 0.6


def _extract_contexts(output: AgentOutput) -> list[str]:
    """从 AgentOutput 中提取检索到的上下文内容。

    优先从 tool_calls 的 result 字段提取（仅当 populate 时有效）。
    降级策略：从答案文本中提取靠前的景点描述片段作为近似上下文。
    """
    # 1. 优先从 tool_calls 中提取 retrieve_knowledge 的结果
    contexts = []
    for tc in output.tool_calls:
        name = (tc.name or "").lower()
        # 匹配各种变体名：retrieve_knowledge, retrieve_knowledge_tool, 知识库...
        is_knowledge = any(k in name for k in ["knowledge", "retrieve", "知识", "景点", "spot"])
        if is_knowledge and tc.result and isinstance(tc.result, str) and tc.result.strip():
            contexts.append(tc.result)
        # 也检查 weather/hotel 等其他检索工具
        if tc.result and isinstance(tc.result, str) and len(tc.result) > 50:
            contexts.append(tc.result)

    # 2. 降级：从 answer 文本中提取
    if not contexts and output.text:
        paragraphs = [p.strip() for p in output.text.split("\n\n") if p.strip()]
        # 取前几个段落作为近似上下文
        contexts = paragraphs[:3]

    return contexts


def _extract_question(fixture: Fixture) -> str:
    """从 fixture 中提取用户问题。"""
    if fixture.input.history:
        # 取最后一条 user 消息
        for turn in reversed(fixture.input.history):
            if turn.get("role") == "user" and turn.get("content"):
                return turn["content"]
    return fixture.input.message


def _has_api_key() -> bool:
    """检查是否配置了 LLM Judge API key。"""
    import os
    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_JUDGE_API_KEY"):
        return True
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("DEEPSEEK_API_KEY="):
                    return True
    return False


@register_evaluator("ragas")
def ragas_evaluator(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """RAGAs 综合评估器。

    计算所有可用的 RAGAs 指标并汇总评分。
    如果未配置 API key，返回 skipped 状态。
    """
    if not _has_api_key():
        return EvalResult(
            passed=True,
            reason="SKIPPED: 未配置 LLM Judge API key，请设置 DEEPSEEK_API_KEY 环境变量",
            details={"skipped": True},
        )

    question = _extract_question(fixture)
    answer = output.text
    contexts = _extract_contexts(output)
    ground_truth = fixture.expected.ground_truth or ""

    if not answer.strip():
        return EvalResult(
            passed=False,
            reason="Agent 输出为空，无法评估",
            details={"error": "empty_answer"},
        )

    from eval.llm_judge import score_all

    results = score_all(
        question=question,
        answer=answer,
        contexts=contexts if contexts else None,
        ground_truth=ground_truth if ground_truth else None,
    )

    # 解析结果
    details = {}
    sub_passed = []
    total_weight = 0
    weighted_pass = 0.0

    # Answer Relevancy
    ar = results.get("answer_relevancy", {})
    ar_score = ar.get("score", 0.0)
    ar_passed = ar_score >= THRESHOLD_ANSWER_RELEVANCY
    details["answer_relevancy"] = {
        "score": ar_score,
        "passed": ar_passed,
        "reason": ar.get("reason", ""),
    }
    sub_passed.append(ar_passed)
    total_weight += 1
    weighted_pass += (1.0 if ar_passed else 0.0)

    # Faithfulness
    f = results.get("faithfulness")
    if f is not None:
        f_score = f.get("score", 0.0)
        f_passed = f_score >= THRESHOLD_FAITHFULNESS
        details["faithfulness"] = {
            "score": f_score,
            "passed": f_passed,
            "claims_count": len(f.get("claims", [])),
            "supported_count": sum(1 for c in f.get("claims", []) if c.get("supported", False)),
        }
        sub_passed.append(f_passed)
        total_weight += 1
        weighted_pass += (1.0 if f_passed else 0.0)

    # Context Recall
    cr = results.get("context_recall")
    if cr is not None:
        cr_score = cr.get("score", 0.0)
        cr_passed = cr_score >= THRESHOLD_CONTEXT_RECALL
        details["context_recall"] = {
            "score": cr_score,
            "passed": cr_passed,
            "covered": cr.get("covered", 0),
            "total": cr.get("total", 0),
        }
        sub_passed.append(cr_passed)
        total_weight += 1
        weighted_pass += (1.0 if cr_passed else 0.0)

    # Context Precision
    cp = results.get("context_precision")
    if cp is not None:
        cp_score = cp.get("score", 0.0)
        cp_passed = cp_score >= THRESHOLD_CONTEXT_PRECISION
        details["context_precision"] = {
            "score": cp_score,
            "passed": cp_passed,
            "relevance": cp.get("ranked_relevance", []),
        }
        sub_passed.append(cp_passed)
        total_weight += 1
        weighted_pass += (1.0 if cp_passed else 0.0)

    # 汇总
    all_passed = all(sub_passed) if sub_passed else False
    overall_score = weighted_pass / total_weight if total_weight > 0 else 0.0
    details["overall"] = {
        "score": round(overall_score, 4),
        "metrics_count": total_weight,
        "passed_count": sum(sub_passed),
    }

    reasons = []
    for name, d in details.items():
        if isinstance(d, dict) and "score" in d and "passed" in d:
            status = "✅" if d["passed"] else "❌"
            reasons.append(f"{status} {name}={d['score']:.2f}")

    return EvalResult(
        passed=all_passed,
        reason="; ".join(reasons),
        details=details,
    )


@register_evaluator("ragas_faithfulness")
def ragas_faithfulness(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """仅评估 Faithfulness（忠实度）。"""
    if not _has_api_key():
        return EvalResult(
            passed=True,
            reason="SKIPPED: 未配置 LLM Judge API key",
            details={"skipped": True},
        )

    answer = output.text
    contexts = _extract_contexts(output)
    if not answer.strip():
        return EvalResult(passed=False, reason="空答案", details={"error": "empty"})

    from eval.llm_judge import score_faithfulness

    result = score_faithfulness(answer, contexts)
    score = result.get("score", 0.0)
    passed = score >= THRESHOLD_FAITHFULNESS
    claims = result.get("claims", [])
    supported = sum(1 for c in claims if c.get("supported", False))

    return EvalResult(
        passed=passed,
        reason=f"Faithfulness={score:.2f} ({supported}/{len(claims)} 有依据)",
        details={
            "score": score,
            "threshold": THRESHOLD_FAITHFULNESS,
            "claims": claims,
            "supported": supported,
            "total_claims": len(claims),
        },
    )


@register_evaluator("ragas_relevancy")
def ragas_relevancy(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """仅评估 Answer Relevancy（答案相关性）。"""
    if not _has_api_key():
        return EvalResult(
            passed=True,
            reason="SKIPPED: 未配置 LLM Judge API key",
            details={"skipped": True},
        )

    question = _extract_question(fixture)
    answer = output.text
    if not answer.strip():
        return EvalResult(passed=False, reason="空答案", details={"error": "empty"})

    from eval.llm_judge import score_answer_relevancy

    result = score_answer_relevancy(question, answer)
    score = result.get("score", 0.0)
    passed = score >= THRESHOLD_ANSWER_RELEVANCY

    return EvalResult(
        passed=passed,
        reason=f"AnswerRelevancy={score:.2f} — {result.get('reason', '')}",
        details={
            "score": score,
            "threshold": THRESHOLD_ANSWER_RELEVANCY,
            "reason": result.get("reason", ""),
        },
    )
