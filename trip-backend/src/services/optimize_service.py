"""Optimize service — 行程优化（对齐 Node.js optimizeService.ts）"""

import asyncio
import json
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import async_session
from src.config.llm import create_llm
from src.models.trip import Trip
from src.utils.logger import trip_log

logger = logging.getLogger(__name__)

MAX_OPTIMIZE_RETRIES = 2


async def _find_trip(trip_id: int, user_id: int = None) -> Optional[Trip]:
    """查找 Trip 记录，可选校验用户所有权。"""
    async with async_session() as session:
        conditions = [Trip.id == trip_id]
        if user_id is not None:
            conditions.append(Trip.user_id == user_id)
        result = await session.execute(
            select(Trip).where(*conditions)
        )
        return result.scalar_one_or_none()


def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON 字符串。"""
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError("未找到 JSON 对象")
    return text[first:last + 1]


def _validate_parsed(parsed: dict) -> None:
    """基本校验优化后的行程 JSON 结构。"""
    required_fields = ["city", "days", "totalBudget", "dailyItinerary", "budgetBreakdown", "tips"]
    if not isinstance(parsed, dict):
        raise ValueError("JSON 根对象必须是字典")
    for field in required_fields:
        if field not in parsed:
            raise ValueError(f"缺少必填字段: {field}")


async def optimize_trip(
    trip_id: int,
    instruction: str = "",
    user_id: Optional[int] = None,
) -> dict:
    """优化行程。

    Args:
        trip_id: 原始行程 ID
        instruction: 优化指令（可选）
        user_id: 用户 ID

    Returns:
        优化后的行程字典（与 recommend 响应格式一致）

    Raises:
        ValueError: 行程不存在 / 多次解析失败
    """
    trip = await _find_trip(trip_id, user_id=user_id)
    if not trip:
        raise ValueError("行程不存在")

    content = trip.content if isinstance(trip.content, dict) else {}
    content_str = json.dumps(content, ensure_ascii=False, indent=2)

    if instruction:
        user_prompt = (
            f"请优化以下行程，根据要求调整：{instruction}\n\n"
            f"原始行程（JSON）：\n{content_str}\n\n"
            "请以 JSON 格式输出优化后的版本，保持结构和预算、天数不变。"
        )
    else:
        user_prompt = (
            f"请优化以下行程，在预算{trip.budget}元、{trip.days}天的框架下给出更好的安排。\n\n"
            f"原始行程（JSON）：\n{content_str}\n\n"
            "请以 JSON 格式输出优化后的版本。"
        )

    system_msg = SystemMessage(
        content=(
            "你是一个专业的旅行规划优化专家。根据用户的要求优化行程，保持 JSON 输出格式不变。"
            "严格遵循字段名/类型/数字不加引号，禁止 markdown 代码块或前后缀文字。"
        )
    )

    parsed: Optional[dict] = None
    last_error: Optional[Exception] = None

    for attempt in range(MAX_OPTIMIZE_RETRIES + 1):
        if attempt == 0:
            human_msg = HumanMessage(content=user_prompt)
        else:
            err_msg = str(last_error) if last_error else "未知错误"
            human_msg = HumanMessage(
                content=(
                    f"上一次的输出解析失败：{err_msg}\n"
                    f"请严格按照 JSON 规范重新输出。\n\n原任务：\n{user_prompt}"
                )
            )

        llm = create_llm(streaming=False)
        llm.temperature = 0.5
        response = await llm.ainvoke([system_msg, human_msg])
        raw_content = response.content if isinstance(response.content, str) else str(response.content)

        try:
            json_str = _extract_json(raw_content)
            candidate = json.loads(json_str)
            _validate_parsed(candidate)
            parsed = candidate
            break
        except Exception as e:
            last_error = e
            trip_log.warning(err=str(e), attempt=attempt + 1, msg="解析失败，准备重试")
            if attempt < MAX_OPTIMIZE_RETRIES:
                await asyncio.sleep(0.8 * (attempt + 1))

    if parsed is None:
        err_msg = str(last_error) if last_error else "未知错误"
        raise ValueError(f"行程优化输出多次解析失败：{err_msg}")

    # 持久化优化后的行程（parent_trip_id 指向原行程）
    created_id: Optional[int] = None
    try:
        async with async_session() as session:
            new_trip = Trip(
                user_id=user_id,
                from_city=trip.from_city,
                city=parsed.get("city", trip.city),
                days=parsed.get("days", trip.days),
                budget=trip.budget,
                content=parsed,
                status="completed",
                parent_trip_id=trip_id,
            )
            session.add(new_trip)
            await session.commit()
            await session.refresh(new_trip)
            created_id = new_trip.id
    except Exception as e:
        trip_log.error(err=str(e), msg="optimize persist failed")

    return {
        "success": True,
        "data": {
            "id": created_id,
            "city": parsed.get("city", ""),
            "days": parsed.get("days", 0),
            "totalBudget": parsed.get("totalBudget"),
            "dailyItinerary": parsed.get("dailyItinerary"),
            "budgetBreakdown": parsed.get("budgetBreakdown"),
            "tips": parsed.get("tips"),
            "warnings": parsed.get("warnings"),
        },
    }
