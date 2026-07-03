"""Validate 节点模块。

对 LLM 输出的 JSON 进行三级校验（修复、Schema、业务逻辑）。
迁移自 Node.js 版本的 nodes/validate.ts。
"""

import json
import re
from typing import Any, Optional

from src.services.agent.types import StepInput


def repair_json(raw: str) -> str:
    """Level 1: JSON 修复（不消耗 Token）。
    
    处理 LLM 常见的 JSON 格式问题，尝试修复后重新 parse。
    每步独立 try-catch，确保单步失败不影响其他修复。
    
    Args:
        raw: 原始 JSON 字符串
        
    Returns:
        修复后的 JSON 字符串
    """
    s = raw
    
    # 1. 去除 markdown 代码块包裹
    try:
        s = re.sub(r"```json\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"```\s*", "", s)
    except Exception:
        pass
    
    # 2. 找到第一个 { 和最后一个 }，去除首尾多余文字
    try:
        first_brace = s.find("{")
        last_brace = s.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            s = s[first_brace:last_brace + 1]
    except Exception:
        pass
    
    # 3. 去除尾逗号: ,] -> ]  ,} -> }
    try:
        s = re.sub(r",\s*([\]}])", r"\1", s)
    except Exception:
        pass
    
    # 4. 仅在文本中没有双引号时，才尝试单引号替换为双引号（保守策略）
    try:
        if '"' not in s:
            s = _replace_single_quotes(s)
    except Exception:
        pass
    
    return s


def _replace_single_quotes(s: str) -> str:
    """将 JSON 字符串中的单引号替换为双引号。
    
    同时避免在双引号字符串内部误替换。
    
    Args:
        s: 输入字符串
        
    Returns:
        替换后的字符串
    """
    result = []
    in_double = False
    in_single = False
    escape = False
    
    for ch in s:
        if escape:
            result.append(ch)
            escape = False
            continue
        
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        
        if in_double:
            result.append(ch)
            if ch == '"':
                in_double = False
            continue
        
        if in_single:
            if ch == "'":
                result.append('"')
                in_single = False
            else:
                # 单引号字符串内遇到双引号需转义
                result.append('\\"' if ch == '"' else ch)
            continue
        
        # 不在任何字符串内
        if ch == '"':
            in_double = True
            result.append(ch)
        elif ch == "'":
            in_single = True
            result.append('"')
        else:
            result.append(ch)
    
    return "".join(result)


def validate_business_logic(parsed: dict) -> list[str]:
    """Level 3: 业务逻辑校验（不阻断，返回警告数组）。
    
    警告数量上限 = min(20, days)，超过只保留前 N 条。
    
    Args:
        parsed: 解析后的行程字典
        
    Returns:
        警告字符串列表
    """
    warnings = []
    
    # 预算分配合理性：budgetBreakdown 各项之和与 totalBudget 偏差不超过 20%
    bb = parsed.get("budgetBreakdown", {})
    if isinstance(bb, dict):
        total_budget = parsed.get("totalBudget", 0)
        sum_budget = bb.get("accommodation", 0) + bb.get("food", 0) + bb.get("transportation", 0) + bb.get("tickets", 0) + bb.get("other", 0)
        
        if total_budget > 0:
            deviation = abs(sum_budget - total_budget) / total_budget
            if deviation > 0.2:
                warnings.append(
                    f"预算分配之和({sum_budget}元)与总预算({total_budget}元)"
                    f"偏差{deviation * 100:.0f}%，超过20%阈值"
                )
    
    # 天数一致性：dailyItinerary 数组长度应与 days 字段匹配
    daily = parsed.get("dailyItinerary", [])
    days = parsed.get("days", 0)
    if isinstance(daily, list) and days > 0 and len(daily) != days:
        warnings.append(
            f"行程天数({len(daily)}天)与声明天数({days}天)不一致"
        )
    
    # 每天至少有一个活动
    if isinstance(daily, list):
        for day_info in daily:
            if isinstance(day_info, dict):
                all_empty = (
                    day_info.get("morning", {}).get("spot", "") == ""
                    and day_info.get("afternoon", {}).get("spot", "") == ""
                    and day_info.get("evening", {}).get("spot", "") == ""
                )
                if all_empty:
                    day_num = day_info.get("day", "?")
                    warnings.append(f"第{day_num}天没有任何活动安排")
    
    # 上限控制：避免长行程生成大量警告
    max_warnings = min(20, days if days > 0 else 20)
    if len(warnings) > max_warnings:
        return warnings[:max_warnings]
    
    return warnings


def validate_with_repair(raw: str) -> dict:
    """完整的三级校验流程。
    
    Level 1: JSON 解析失败 -> repairJson（不消耗 Token）
    Level 2: Schema 校验失败 -> 抛异常（由外层 plannerGraph 处理 LLM 重试）
    Level 3: 业务逻辑校验 -> 附加 warnings（不阻断）
    
    Args:
        raw: LLM 输出的原始字符串
        
    Returns:
        包含 parsed, repaired, warnings 的字典
        
    Raises:
        ValueError: JSON 解析或 Schema 校验失败
    """
    repaired = False
    json_obj = None
    
    # 先尝试直接解析（假设输出是干净的 JSON）
    try:
        # 尝试提取 JSON（处理前后缀文字）
        json_str = _extract_json(raw)
        json_obj = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as extract_error:
        # Level 1: JSON 解析失败 -> repairJson 后重试（不消耗 Token）
        repaired = True
        try:
            json_str = _extract_json_string(raw)
            repaired_str = repair_json(json_str)
            json_obj = json.loads(repaired_str)
        except (json.JSONDecodeError, ValueError) as repair_error:
            # repairJson 也无法修复，抛出原始错误
            raise ValueError(
                f"JSON 修复失败: {repair_error}\n"
                f"(原始错误: {extract_error})"
            )
    
    # Level 2: Schema 校验（简化版，完整版需要用 Pydantic）
    # 这里做基本的字段检查
    if not isinstance(json_obj, dict):
        raise ValueError("JSON 根对象必须是字典")
    
    # 检查必填字段
    required_fields = ["city", "days", "totalBudget", "dailyItinerary", "budgetBreakdown", "tips"]
    for field in required_fields:
        if field not in json_obj:
            raise ValueError(f"缺少必填字段: {field}")
    
    # Level 3: 业务逻辑校验（不阻断）
    warnings = validate_business_logic(json_obj)
    if warnings:
        if "warnings" not in json_obj or not json_obj["warnings"]:
            json_obj["warnings"] = warnings
        else:
            json_obj["warnings"] = list(json_obj["warnings"]) + warnings
    
    return {"parsed": json_obj, "repaired": repaired, "warnings": warnings}


def _extract_json(text: str) -> str:
    """从文本中提取 JSON 字符串。
    
    Args:
        text: 可能包含 JSON 的文本
        
    Returns:
        提取的 JSON 字符串
        
    Raises:
        ValueError: 无法提取 JSON
    """
    # 查找第一个 { 和最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    
    if first == -1 or last == -1 or last <= first:
        raise ValueError("未找到 JSON 对象")
    
    return text[first:last + 1]


def _extract_json_string(text: str) -> str:
    """从文本中提取 JSON 字符串（与 _extract_json 相同，为兼容性保留）。
    
    Args:
        text: 可能包含 JSON 的文本
        
    Returns:
        提取的 JSON 字符串
    """
    return _extract_json(text)


def validate_node(state: dict, config: dict) -> dict:
    """Validate 节点实现：校验 LLM 输出的 JSON。
    
    Args:
        state: 当前状态
        config: LangGraph 配置
        
    Returns:
        更新的状态字段
    """
    raw_output = state.get("raw_output", "")
    if not raw_output:
        return {"parsed": None, "errors": [*state.get("errors", []), "输出为空"]}
    
    try:
        result = validate_with_repair(raw_output)
        
        # 记录修复事件
        if result["repaired"]:
            configurable = config.get("configurable", {})
            trace_recorder = configurable.get("trace_recorder")
            if trace_recorder:
                trace_recorder.add({
                    "step": 0,
                    "type": "complete",
                    "name": "json_repair",
                    "output": "JSON was repaired by Level 1 retry",
                })
        
        return {"parsed": result["parsed"], "errors": state.get("errors", [])}
        
    except ValueError as e:
        error_msg = str(e)
        return {"parsed": None, "errors": [*state.get("errors", []), error_msg]}


def validate_output(raw: str) -> dict:
    """验证输出（简化版，直接返回解析结果）。
    
    Args:
        raw: 原始输出字符串
        
    Returns:
        包含 parsed 的字典
    """
    result = validate_with_repair(raw)
    return {"parsed": result["parsed"]}


def build_retry_message(zod_error: str, original_request: str) -> str:
    """构建重试消息（当 JSON 校验失败时）。
    
    Args:
        zod_error: Schema 校验错误信息
        original_request: 原始用户请求
        
    Returns:
        重试消息字符串
    """
    return (
        f"你上次的输出无法通过校验：\n{zod_error}\n\n"
        f"请严格按 system prompt 中的字段定义重新输出纯 JSON：\n"
        f"- 数字字段不加引号（city/days/totalBudget/day/budgetBreakdown.*）\n"
        f"- dailyItinerary 必须是对象数组，每天对象含 day/date/morning/afternoon/evening\n"
        f"- budgetBreakdown 必须含 accommodation/food/transportation/tickets/other 5 个数字\n"
        f"- 禁止 markdown 代码块、禁止前后缀文字\n\n"
        f"用户请求：{original_request}"
    )
