"""arq worker 任务 —— 对话结束后异步后处理（摘要压缩 + 关键决策记录）。

改造动机（决策文档 §3.2 / M2）：
- 原 trip_service._post_chat_tasks 用 `asyncio.create_task(_run())` 启动后台任务，
  FastAPI worker 进程崩溃（OOM / 部署重启 / SIGKILL）任务就蒸发——
  对话摘要没压、关键决策没记，**没有任何重试 / 状态查询 / 告警**。
- 改为入队：API 流式响应结束后立即入队（< 5ms），arq worker 异步消费。
- 失败重试 + 死信告警 + 结果可查（`arq:result:{job_id}`）。

设计要点：
- 保留原原子性：compress + decision 仍由同一个 worker 函数顺序执行。
  拆成 2 个独立 job 反而会让"压缩成功但决策失败"出现中间态，且 job_id 难设计。
- 幂等键：`post_chat:followup:{conversation_id}` —— 同一对话多次流式结束
  （客户端重连 / 续传）只执行 1 次。`is_planning` 是 bool 入参（不算幂等键一部分）。
- 入参预计算：`is_planning_request` 在 API 端（trip_service）算好传入，
  避免 worker 内再 import router 链路（轻量化）。
- 失败抛错让 arq 重试（worker.py max_tries=1 → 失败入死信可查）。
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 在 worker 进程顶部 import 全部 model，确保 SQLAlchemy mapper 完整初始化
# （避免 User→TokenUsageLog 关系链断裂导致 InvalidRequestError，参考 conftest.py）
import src.models.user  # noqa: F401
import src.models.conversation  # noqa: F401
import src.models.message  # noqa: F401
import src.models.trip  # noqa: F401
import src.models.spot  # noqa: F401
import src.models.spot_doc  # noqa: F401
import src.models.password_reset  # noqa: F401
import src.models.role  # noqa: F401
import src.models.feedback  # noqa: F401
import src.models.agent_step  # noqa: F401
import src.models.token_usage_log  # noqa: F401


async def post_chat_followup(
    ctx: Optional[dict],
    conversation_id: int,
    user_message: str,
    is_planning: bool,
) -> dict:
    """对话结束后的后处理：摘要压缩 + 关键决策记录。

    适用场景：chat 流式响应 __done__ / __error__ 触发。
    失败抛错会被 arq 视为任务失败（worker.py max_tries=1 → 入死信可查）。

    Args:
        ctx: arq 注入的上下文（含 job_id / job_try 等）；降级路径为 None 时构造 fake ctx
        conversation_id: 对话 ID（主键）
        user_message: 用户最后一条消息（用于关键决策文案）
        is_planning: 是否为行程规划请求（在 API 端预计算）

    Returns:
        {"conversation_id": int, "compressed": bool, "decision_recorded": bool,
         "decision_skipped": bool, "attempt": int}

    Raises:
        Exception: summary_service 内部异常（被 arq 捕获并入死信）
    """
    # 兼容降级路径：ctx 为 None 时构造 fake ctx
    if ctx is None:
        ctx = {"job_id": None, "job_try": 1, "degraded": True}

    # 懒导入：避免模块 import-time 把整个 db / summary 链路拉起来
    from src.config.database import async_session
    from src.services.summary_service import summary_service

    attempt = ctx.get("job_try", 1)
    compressed = False
    decision_recorded = False
    decision_skipped = not is_planning  # is_planning=False 时直接跳过

    # 1. 摘要压缩（始终执行）
    try:
        async with async_session() as session:
            await summary_service.compress_conversation(session, conversation_id)
        compressed = True
        logger.info(
            "[post_chat_followup] compressed conv_id=%s attempt=%s",
            conversation_id, attempt,
        )
    except Exception as e:
        # 摘要失败是关键故障（决策依附摘要存在），整体抛出让 arq 入死信
        logger.error(
            "[post_chat_followup] compress FAILED conv_id=%s error=%s",
            conversation_id, e, exc_info=True,
        )
        raise

    # 2. 关键决策记录（仅 is_planning=True）
    if is_planning:
        decision = f"用户发起行程规划：{user_message}"
        try:
            async with async_session() as session:
                await summary_service.append_key_decision(
                    session, conversation_id, decision,
                )
            decision_recorded = True
            decision_skipped = False
            logger.info(
                "[post_chat_followup] decision recorded conv_id=%s attempt=%s",
                conversation_id, attempt,
            )
        except Exception as e:
            # 决策失败不算致命（compress 已成功），warn 但不抛
            # 决策丢失是“次要损失”（不影响对话主流程），可后续手动补
            logger.warning(
                "[post_chat_followup] decision FAILED conv_id=%s error=%s",
                conversation_id, e, exc_info=True,
            )
    
        # 3. 偏好提取（仅 planning 相关对话触发，异步不阻塞）
        try:
            await _extract_and_save_preferences(conversation_id)
            logger.info(
                "[post_chat_followup] preferences extracted conv_id=%s",
                conversation_id,
            )
        except Exception as e:
            # 偏好提取失败不影响主流程
            logger.warning(
                "[post_chat_followup] preference extraction FAILED conv_id=%s error=%s",
                conversation_id, e,
            )
    else:
        logger.debug(
            "[post_chat_followup] decision skipped (not planning) conv_id=%s",
            conversation_id,
        )

    return {
        "conversation_id": conversation_id,
        "compressed": compressed,
        "decision_recorded": decision_recorded,
        "decision_skipped": decision_skipped,
        "attempt": attempt,
    }


# ---------------------------------------------------------------------------
# 偏好提取
# ---------------------------------------------------------------------------

_PREFERENCE_PROMPT = """从以下对话中提取用户旅行偏好。只提取明确表达的偏好，不要推测。
输出纯 JSON（只包含有值的字段）：
{"interests": ["..."], "avoid": ["..."], "pace": "relaxed|normal|compact", "budget_level": "budget|moderate|luxury", "companions": "..."}
如果无明确偏好，输出 {}。
只输出 JSON，不要其他文字。"""


async def _extract_and_save_preferences(conversation_id: int) -> None:
    """从对话中提取用户偏好并增量合并到 User.preferences。"""
    import json
    from sqlalchemy import select
    from src.config.database import async_session
    from src.models.conversation import Conversation
    from src.models.message import Message
    from src.models.user import User
    from src.config.llm import create_llm
    from langchain_core.messages import HumanMessage

    async with async_session() as session:
        # 1. 加载对话的 user_id 和最近消息
        conv_result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = conv_result.scalar_one_or_none()
        if not conv or not conv.user_id:
            return

        msg_result = await session.execute(
            select(Message.content, Message.role)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)
        )
        messages = msg_result.all()
        if not messages:
            return

        # 拼接对话内容（取最近 10 条）
        dialog_text = "\n".join(
            f"{'user' if role == 'user' else 'assistant'}: {content[:200]}"
            for content, role in reversed(messages)
        )

        # 2. LLM 提取偏好
        llm = create_llm(streaming=False)
        resp = await llm.ainvoke([
            HumanMessage(content=f"{_PREFERENCE_PROMPT}\n\n对话内容：\n{dialog_text}")
        ])
        raw = resp.content if isinstance(resp.content, str) else ""

        # 解析 JSON
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end <= start:
                return
            new_prefs = json.loads(raw[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return

        if not new_prefs:
            return  # 无明确偏好

        # 3. 增量合并到 User.preferences
        user_result = await session.execute(
            select(User).where(User.id == conv.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return

        existing = user.preferences or {}

        # 合并逻辑：interests/avoid 追加去重，其他字段覆盖
        if "interests" in new_prefs:
            old_interests = existing.get("interests", [])
            if isinstance(old_interests, list):
                merged = list(dict.fromkeys(old_interests + new_prefs["interests"]))
                existing["interests"] = merged
        if "avoid" in new_prefs:
            old_avoid = existing.get("avoid", [])
            if isinstance(old_avoid, list):
                merged = list(dict.fromkeys(old_avoid + new_prefs["avoid"]))
                existing["avoid"] = merged
        for key in ("pace", "budget_level", "companions"):
            if key in new_prefs:
                existing[key] = new_prefs[key]

        user.preferences = existing
        await session.commit()
        logger.info(
            "[preference_extract] user_id=%s updated prefs=%s",
            conv.user_id, list(new_prefs.keys()),
        )
