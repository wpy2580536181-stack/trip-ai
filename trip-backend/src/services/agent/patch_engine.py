"""Patch 引擎：直接对行程 JSON 应用结构化修改。

用于 Slot 级局部修改，不走 LLM 重生成。
"""

import copy
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

SUPPORTED_OPS = frozenset({"replace_slot", "remove_slot", "swap_slot"})


class PatchError(Exception):
    """Patch 应用失败，应降级为 modify。"""
    pass


def apply_patch(trip: dict, op: str, day: int, **kwargs) -> dict:
    """对行程应用一个 patch 操作。

    Args:
        trip: 原行程 dict（不会被修改）
        op: 操作类型（replace_slot / remove_slot / swap_slot）
        day: 目标天数（从 1 开始）
        **kwargs: 操作参数
            - period: "morning" / "afternoon" / "evening"（replace/remove 需要）
            - spot_name: 景点名称（replace 需要）
            - period_b: 第二个时段（swap 需要）

    Returns:
        修改后的新行程 dict

    Raises:
        PatchError: 校验不通过或操作不合法
    """
    if op not in SUPPORTED_OPS:
        raise PatchError(f"不支持的 patch 操作: {op}")

    if op == "replace_slot":
        return _apply_replace(trip, day, kwargs)
    elif op == "remove_slot":
        return _apply_remove(trip, day, kwargs)
    elif op == "swap_slot":
        return _apply_swap(trip, day, kwargs)

    raise PatchError(f"未实现的操作: {op}")


def _get_day(trip: dict, day: int) -> dict:
    """获取指定天的行程对象。"""
    itinerary = trip.get("dailyItinerary", [])
    for d in itinerary:
        if d.get("day") == day:
            return d
    raise PatchError(f"第 {day} 天不存在")


def _validate_no_duplicate(itinerary: list, day: int, new_spot: str, exclude_period: Optional[str] = None) -> None:
    """检查同一天内是否有重复景点（跨时段去重）。"""
    for d in itinerary:
        if d.get("day") != day:
            continue
        for period in ("morning", "afternoon", "evening"):
            if period == exclude_period:
                continue
            slot = d.get(period)
            if slot and slot.get("spot") and slot["spot"] == new_spot:
                raise PatchError(f"第 {day} 天 {period} 已存在景点「{new_spot}」，请选择其他景点")


def _apply_replace(trip: dict, day: int, kwargs: dict) -> dict:
    period = kwargs.get("period", "")
    spot_name = kwargs.get("spot_name", "")
    description = kwargs.get("description", "")

    if period not in ("morning", "afternoon", "evening"):
        raise PatchError(f"无效的时段: {period}")
    if not spot_name:
        raise PatchError("replace_slot 需要 spot_name")

    merged = copy.deepcopy(trip)
    day_obj = _get_day(merged, day)
    slot = day_obj.get(period, {})

    _validate_no_duplicate(
        merged.get("dailyItinerary", []), day, spot_name,
        exclude_period=period,
    )

    slot["spot"] = spot_name
    if description:
        slot["description"] = description
    day_obj[period] = slot

    logger.info("patch|replace day=%d period=%s spot=%s", day, period, spot_name)
    return merged


def _apply_remove(trip: dict, day: int, kwargs: dict) -> dict:
    period = kwargs.get("period", "")

    if period not in ("morning", "afternoon", "evening"):
        raise PatchError(f"无效的时段: {period}")

    merged = copy.deepcopy(trip)
    day_obj = _get_day(merged, day)
    day_obj[period] = {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""}

    logger.info("patch|remove day=%d period=%s", day, period)
    return merged


def _apply_swap(trip: dict, day: int, kwargs: dict) -> dict:
    period_a = kwargs.get("period", "")
    period_b = kwargs.get("period_b", "")

    if period_a not in ("morning", "afternoon", "evening"):
        raise PatchError(f"无效的时段 A: {period_a}")
    if period_b not in ("morning", "afternoon", "evening"):
        raise PatchError(f"无效的时段 B: {period_b}")
    if period_a == period_b:
        raise PatchError("不能对调同一个时段")

    merged = copy.deepcopy(trip)
    day_obj = _get_day(merged, day)
    slot_a = day_obj.get(period_a, {})
    slot_b = day_obj.get(period_b, {})
    day_obj[period_a], day_obj[period_b] = slot_b, slot_a

    logger.info("patch|swap day=%d %s<->%s", day, period_a, period_b)
    return merged
