"""对话摘要压缩服务。

对齐 Node.js src/services/summaryService.ts。
分层摘要：关键决策 + 对话脉络，append 模式。
"""

import asyncio
import re
from datetime import date
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage as LCHumanMessage, SystemMessage as LCSystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.llm import create_llm
from src.models.conversation import Conversation
from src.models.message import Message
from src.utils.logger import summary_log as log
from src.utils.tokens import (
    DEFAULT_COMPACTION_TARGET_TOKENS,
    estimate_tokens,
    get_history_max_tokens,
)

MAX_RETRIES = 2
RETRY_BASE_MS = 1000
APPEND_MARKER = "### 追加于"


class CompactionSelection(TypedDict):
    """压缩选择结果。"""
    to_compact: list
    to_keep: list
    freed_tokens: int


class SummaryService:
    """对话摘要压缩服务。

    分层摘要：关键决策 + 对话脉络，append 模式。
    """

    def __init__(self):
        self.max_retries = MAX_RETRIES
        self.retry_base_ms = RETRY_BASE_MS
        self.append_marker = APPEND_MARKER

    # ==================== 公开方法 ====================

    async def append_key_decision(
        self,
        db: AsyncSession,
        conversation_id: int,
        decision: str,
    ) -> None:
        """追加关键决策到对话摘要。

        当用户确认行程修改时调用。

        Args:
            db: 数据库会话
            conversation_id: 对话 ID
            decision: 决策文本
        """
        try:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()

            previous_summary = conversation.summary if conversation else None
            marker = self._format_date_marker()
            new_summary = self._append_chunk(previous_summary, marker, decision)

            if conversation:
                conversation.summary = new_summary
                conversation.summary_error = False
                from sqlalchemy import func
                conversation.summary_at = func.now()
                await db.commit()

            log.info(
                conversationId=conversation_id,
                decisionLen=len(decision),
                msg="关键决策已追加到摘要",
            )
        except Exception as e:
            log.error(err=str(e), conversationId=conversation_id, msg="追加关键决策失败")
            raise

    async def compress_context(
        self,
        db: AsyncSession,
        conversation_id: int,
        messages: list[dict],
    ) -> str:
        """压缩对话脉络（将指定消息压缩为摘要）。

        Args:
            db: 数据库会话
            conversation_id: 对话 ID
            messages: 待压缩消息列表 [{"role": str, "content": str, "id": int}, ...]

        Returns:
            新的 recap chunk（对话脉络），如果失败则返回空字符串
        """
        try:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            previous_summary = conversation.summary if conversation else None
            previous_recap = conversation.recap if conversation else None

            dialog_text = "\n".join(
                f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
                for m in messages
            )

            system_msg = (
                "你是一个对话摘要助手。请分析以下对话，按指定格式输出两层摘要。\n\n"
                "## 输出格式（严格遵守）\n"
                "必须输出两段，每段以 ### 开头的标题行作为锚点，标题与正文之间换行：\n\n"
                "### 关键决策\n"
                "<记录本次对话产生的关键决策：目的地、天数、预算、偏好、行程安排、住宿选择等已确定的事项，80-150 字>\n\n"
                "### 对话脉络\n"
                "<记录本次对话的脉络：讨论过的主题与方向、用户的兴趣演变、问过什么、还没问什么、关注点的变化，80-150 字>\n\n"
                "## 追加规则\n"
                "- 本次输出会追加到已有摘要/脉络的末尾，所以请只关注本次对话的新信息，不要重复已有内容\n"
                "- 不要加 markdown 代码块、不要加任何前后缀解释文字，输出完直接结束"
            )

            prompt = f"对话：\n{dialog_text}\n\n请按格式输出关键决策和对话脉络两段："

            new_summary_chunk: Optional[str] = None
            new_recap_chunk: Optional[str] = None

            for attempt in range(self.max_retries + 1):
                try:
                    llm = create_llm(streaming=False)
                    llm.temperature = 0.3
                    response = await llm.ainvoke([
                        LCSystemMessage(content=system_msg),
                        LCHumanMessage(content=prompt),
                    ])
                    text = response.content.strip() if isinstance(response.content, str) else str(response.content).strip()
                    parsed = self._parse_layered_summary(text)

                    # 至少拿到关键决策段才算成功；脉络段允许缺失（降级）
                    if parsed["summary"] and len(parsed["summary"]) >= 20:
                        new_summary_chunk = parsed["summary"]
                        new_recap_chunk = (
                            parsed["recap"]
                            if parsed["recap"] and len(parsed["recap"]) >= 20
                            else None
                        )
                        break

                    log.warn(
                        attempt=attempt + 1,
                        hasSummary=bool(parsed["summary"]),
                        hasRecap=bool(parsed["recap"]),
                        msg="解析未得到关键决策段",
                    )
                except Exception as e:
                    log.warn(err=str(e), attempt=attempt + 1, msg="压缩失败")

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_base_ms * (attempt + 1) / 1000)

            if new_summary_chunk:
                await self._commit_append_layered(
                    db,
                    conversation_id,
                    new_summary_chunk,
                    new_recap_chunk,
                    previous_summary,
                    previous_recap,
                )

                if not new_recap_chunk:
                    log.warn(conversationId=conversation_id, msg="本次仅写入 summary，recap 解析缺失或过短")

                # 摘要成功写入后才物理标记这些消息为 excluded（failure-safe）
                old_ids = [m["id"] for m in messages]
                if old_ids:
                    await db.execute(
                        update(Message)
                        .where(
                            Message.id.in_(old_ids),
                            Message.excluded_from_context != True,  # noqa: E712
                        )
                        .values(excluded_from_context=True)
                    )
                    await db.commit()

                log.info(
                    conversationId=conversation_id,
                    compacted=len(old_ids),
                    msg="旧消息标记为 excludedFromContext",
                )

                return new_recap_chunk or ""
            else:
                log.error(attempts=self.max_retries + 1, msg="重试全部失败，标记 summary_error")
                await self._mark_summary_failed(db, conversation_id)
                return ""

        except Exception as e:
            log.error(err=str(e), msg="压缩流程异常")
            try:
                await self._mark_summary_failed(db, conversation_id)
            except Exception:
                pass
            return ""

    async def get_summary(
        self,
        db: AsyncSession,
        conversation_id: int,
    ) -> dict:
        """获取对话摘要（用于注入到 LLM prompt）。

        Args:
            db: 数据库会话
            conversation_id: 对话 ID

        Returns:
            {"summary": str | None, "recap": str | None}
        """
        try:
            result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            return {
                "summary": conversation.summary if conversation else None,
                "recap": conversation.recap if conversation else None,
            }
        except Exception as e:
            log.error(err=str(e), conversationId=conversation_id, msg="获取摘要失败")
            return {"summary": None, "recap": None}

    async def compress_conversation(
        self,
        db: AsyncSession,
        conversation_id: int,
    ) -> None:
        """对外暴露的完整压缩流程。

        检查是否需要压缩，如果需要则执行压缩。

        Args:
            db: 数据库会话
            conversation_id: 对话 ID
        """
        try:
            max_tokens = get_history_max_tokens()
            ctx = await _get_context_messages(db, conversation_id, max_tokens)

            # 大多数轮次：TAIL 总量未超预算，跳过整个 LLM 调用
            if not ctx["needs_compaction"]:
                return
            if not ctx["messages"]:
                return

            # 目标：把 TAIL 压到 targetTokens（~12K），留 25% buffer 避免下一两轮又触发
            target_tokens = DEFAULT_COMPACTION_TARGET_TOKENS
            selection = select_compaction_range(ctx["messages"], ctx["total_tokens"], target_tokens)
            if not selection["to_compact"]:
                return

            await self.compress_context(
                db,
                conversation_id,
                selection["to_compact"],
            )
        except Exception as e:
            log.error(err=str(e), msg="压缩对话异常")
            raise

    # ==================== 私有方法 ====================

    def _format_date_marker(self) -> str:
        return f"{self.append_marker} {date.today().isoformat()}"

    def _append_chunk(self, previous: Optional[str], marker: str, chunk: str) -> str:
        return f"{previous}\n\n{marker}\n{chunk}" if previous else chunk

    def _parse_layered_summary(self, raw: str) -> dict:
        """解析 LLM 输出的分层摘要。

        Args:
            raw: LLM 原始输出文本

        Returns:
            {"summary": str | None, "recap": str | None}
        """
        text = raw.strip()

        # 去掉外层 ``` 代码块（容错）
        fence = re.match(r"^```[a-zA-Z]*\n([\s\S]*?)\n```\s*$", text)
        if fence:
            text = fence.group(1).strip()

        summary_match = re.search(r"###\s*关键决策\s*\n([\s\S]*?)(?=\n###\s*对话脉络|$)", text)
        recap_match = re.search(r"###\s*对话脉络\s*\n([\s\S]*?)$", text)

        summary = summary_match.group(1).strip() if summary_match else None
        recap = recap_match.group(1).strip() if recap_match else None

        return {"summary": summary, "recap": recap}

    async def _commit_append_layered(
        self,
        db: AsyncSession,
        conversation_id: int,
        new_summary_chunk: Optional[str],
        new_recap_chunk: Optional[str],
        previous_summary: Optional[str],
        previous_recap: Optional[str],
    ) -> None:
        marker = self._format_date_marker()

        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            return

        from sqlalchemy import func
        conversation.summary_error = False
        conversation.summary_at = func.now()

        if new_summary_chunk:
            conversation.summary = self._append_chunk(previous_summary, marker, new_summary_chunk)
        if new_recap_chunk:
            conversation.recap = self._append_chunk(previous_recap, marker, new_recap_chunk)

        await db.commit()

        log.info(
            conversationId=conversation_id,
            summaryLen=len(new_summary_chunk) if new_summary_chunk else 0,
            recapLen=len(new_recap_chunk) if new_recap_chunk else 0,
            mode="append" if previous_summary else "new",
            msg="分层摘要更新",
        )

    async def _mark_summary_failed(self, db: AsyncSession, conversation_id: int) -> None:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation:
            conversation.summary_error = True
            await db.commit()


# ==================== 纯函数 ====================


def select_compaction_range(
    messages: list[dict],
    total_tokens: int,
    target_tokens: int,
) -> CompactionSelection:
    """纯函数：根据 TAIL 当前总量和目标 token 数，从最老开始贪心选出要压缩的消息。

    Args:
        messages: 消息列表（按时间正序），每条含 "content" 字段
        total_tokens: 当前总 token 数
        target_tokens: 压缩目标 token 数

    Returns:
        CompactionSelection: {"to_compact": list, "to_keep": list, "freed_tokens": int}
    """
    if total_tokens <= target_tokens:
        return {"to_compact": [], "to_keep": messages, "freed_tokens": 0}

    tokens_to_free = total_tokens - target_tokens
    freed = 0
    count = 0
    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        freed += estimate_tokens(content)
        count += 1
        if freed >= tokens_to_free:
            break

    # 边界保护：单条消息就超过 target 时，至少压缩 1 条
    if count == 0:
        count = 1

    return {
        "to_compact": messages[:count],
        "to_keep": messages[count:],
        "freed_tokens": freed,
    }


async def _get_context_messages(
    db: AsyncSession,
    conversation_id: int,
    max_tokens: int,
) -> dict:
    """获取对话上下文消息（单调追加模式，不 shift）。

    保持 prefix 稳定以命中 LLM prompt cache。
    - 返回所有未压缩的原始消息（按时间正序），让 LLM 看到完整 TAIL
    - 仅返回 needs_compaction 标志告诉调用方"该压缩了"，由调用方决定压缩多少
    - 已压缩的旧消息（excluded_from_context=true）从结果中过滤掉

    Args:
        db: 数据库会话
        conversation_id: 对话 ID
        max_tokens: 最大 token 数

    Returns:
        {"messages": list, "total_tokens": int, "needs_compaction": bool}
    """
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.excluded_from_context != True,  # noqa: E712
        )
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

    # 过滤掉空 content 消息（占位消息）
    real_messages = [
        {"role": m.role, "content": m.content, "id": m.id}
        for m in messages
        if m.content
    ]

    total_tokens = sum(estimate_tokens(m["content"]) for m in real_messages)

    return {
        "messages": real_messages,
        "total_tokens": total_tokens,
        "needs_compaction": total_tokens > max_tokens,
    }


# 导出单例
summary_service = SummaryService()


async def compress_conversation(db: AsyncSession, conversation_id: int) -> None:
    """便捷函数：压缩对话（委托给单例）。"""
    await summary_service.compress_conversation(db, conversation_id)
