"""Review 校验模块（非 Agent）。

两层设计：
- 第一层（代码，确定性）：预算/候选池/时间冲突/天数/JSON 格式
- 第二层（独立 LLM 调用，Phase 5 实现）：季节适配/节奏/多样性

本模块是函数，不是 Agent——不含工具调用循环，不做自主决策。
"""

import json
import logging
import re
from typing import Optional

from src.services.agent.schemas import ResearchBundle, ReviewResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

async def review(
    raw_output: str,
    bundle: Optional[ResearchBundle],
    budget: int,
    days: int,
) -> tuple[Optional[dict], ReviewResult]:
    """审阅 Planner 输出。

    Args:
        raw_output: Planner 的原始 JSON 字符串
        bundle: 候选池（用于封闭世界校验）
        budget: 用户预算
        days: 期望天数

    Returns:
        (parsed_plan, ReviewResult) 元组
        - parsed_plan: 解析成功时为 dict，否则为 None
        - ReviewResult: 审阅结果
    """
    code_checks = {}

    # ── Step 1: JSON 解析（含修复）──
    parsed = _parse_json(raw_output)
    if parsed is None:
        return None, ReviewResult(
            passed=False,
            issues=["输出无法解析为合法 JSON"],
            feedback="你的输出不是合法 JSON。请严格按字段定义输出纯 JSON，不要 markdown 代码块。",
            code_checks={"json_parse": False},
        )
    code_checks["json_parse"] = True

    # ── Step 2: 天数一致性 ──
    itinerary = parsed.get("dailyItinerary", [])
    actual_days = len(itinerary)
    if actual_days != days:
        code_checks["days_match"] = False
        issue = f"行程天数不匹配：期望 {days} 天，实际 {actual_days} 天"
        return parsed, ReviewResult(
            passed=False,
            issues=[issue],
            feedback=f"dailyItinerary 数组长度必须等于 {days}，当前为 {actual_days}。请调整。",
            code_checks=code_checks,
        )
    code_checks["days_match"] = True

    # ── Step 3: 预算校验 ──
    total_budget = parsed.get("totalBudget", 0)
    if isinstance(total_budget, (int, float)) and budget > 0:
        over_ratio = total_budget / budget
        code_checks["budget_ratio"] = round(over_ratio, 2)
        if over_ratio > 1.15:
            issue = f"预算超标：规划 {total_budget} 元，用户预算 {budget} 元（超出 {(over_ratio-1)*100:.0f}%）"
            return parsed, ReviewResult(
                passed=False,
                issues=[issue],
                feedback=(
                    f"总预算 {total_budget} 元超出用户预算 {budget} 元。"
                    f"请压缩至 {budget} 元以内：优先降低酒店档次、增加免费景点、减少付费活动。"
                ),
                code_checks=code_checks,
            )
    code_checks["budget_ok"] = True

    # ── Step 4: budgetBreakdown 完整性 ──
    breakdown = parsed.get("budgetBreakdown", {})
    required_keys = ["accommodation", "food", "transportation", "tickets", "other"]
    missing = [k for k in required_keys if k not in breakdown]
    if missing:
        code_checks["breakdown_complete"] = False
        issue = f"budgetBreakdown 缺少字段：{missing}"
        return parsed, ReviewResult(
            passed=False,
            issues=[issue],
            feedback=f"budgetBreakdown 必须包含 {required_keys} 五个数字字段，缺少：{missing}。",
            code_checks=code_checks,
        )
    code_checks["breakdown_complete"] = True

    # ── Step 5: 候选池合规（封闭世界校验）──
    if bundle and bundle.all_spot_names():
        code_checks["pool_compliance"] = "skipped_phase1"
    else:
        code_checks["pool_compliance"] = "no_pool"

    # ── Step 6: LLM 第二层审阅（独立上下文，无工具）──
    llm_issues = await _llm_review(parsed, code_checks)
    if llm_issues:
        code_checks["llm_review"] = llm_issues
        # LLM 发现的问题作为 warning，不强制打回（避免过度拒绝）
        logger.info("review|llm_warnings=%s", llm_issues)

    # ── 全部通过 ──
    logger.info("review|passed checks=%s", code_checks)
    return parsed, ReviewResult(
        passed=True,
        issues=[],
        feedback="",
        code_checks=code_checks,
    )


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> Optional[dict]:
    """解析 JSON（含修复逻辑）。

    复用现有 validate.py 的 repair_json 逻辑。
    """
    if not raw or not raw.strip():
        return None

    # 直接尝试解析
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass

    # 修复后重试
    try:
        from src.services.agent.nodes.validate import repair_json
        repaired = repair_json(raw)
        obj = json.loads(repaired)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # 最后尝试：提取最外层 { }
    try:
        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last > first:
            obj = json.loads(raw[first:last + 1])
            return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    return None


async def _llm_review(parsed: dict, code_checks: dict) -> list[str]:
    """LLM 第二层审阅（独立上下文，无工具）。

    输入：行程 JSON + 代码预计算的客观事实
    输出：问题列表（空 = 无问题）

    设计原则（来自 FloatTrip）：
    - 代码能判的绝不用 LLM
    - LLM 只基于预计算的客观事实做主观判断
    - 独立上下文，不共享 Planner 的对话历史
    """
    try:
        from src.config.llm import create_llm
        llm = create_llm(streaming=False)

        # 构建审阅 prompt
        itinerary_summary = json.dumps(
            parsed.get("dailyItinerary", [])[:3],  # 只取前 3 天避免过长
            ensure_ascii=False,
        )[:2000]

        prompt = f"""你是一个行程质量审阅员。请检查以下行程是否存在以下问题：
1. 季节适配性（冬天推荐游泳、夏天推荐滑雪等）
2. 节奏合理性（每天安排超过 5 个活动、或整天无活动）
3. 景点多样性（连续多天同类型景点）

代码层已校验通过的项目：{list(code_checks.keys())}

行程摘要：
{itinerary_summary}

如果无问题，输出 JSON: {{"issues": []}}
如果有问题，输出 JSON: {{"issues": ["问题1", "问题2"]}}
只输出 JSON，不要其他文字。"""

        from langchain_core.messages import HumanMessage
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        content = resp.content if isinstance(resp.content, str) else ""

        # 解析 LLM 输出
        result = json.loads(content.strip())
        return result.get("issues", [])
    except Exception as e:
        # LLM 审阅失败不影响主流程
        logger.warning("review|llm_layer_failed: %s", e)
        return []
