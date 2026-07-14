"""Trip service — chatStream + recommend（对齐 Node.js tripService.ts）"""

import asyncio
import time
import logging
from typing import Optional, AsyncGenerator, Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import async_session
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.trip import Trip
from src.services.agent.agent_engine import get_agent_engine
from src.services.agent.nodes.router import is_planning_request
from src.services.summary_service import summary_service
from src.services.conversation_service import auto_title
from src.utils.logger import trip_log

logger = logging.getLogger(__name__)

# 增量持久化 flush 间隔（毫秒）
ASSISTANT_PERSIST_FLUSH_INTERVAL_MS = 3000


# ---------------------------------------------------------------------------
# 内部辅助：对话/消息 CRUD（使用独立 session，不依赖请求生命周期）
# ---------------------------------------------------------------------------

async def _get_or_create_conversation(
    user_id: int,
    conversation_id: Optional[int],
) -> Conversation:
    """获取或创建对话。"""
    async with async_session() as session:
        if conversation_id:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                return conv
        # 创建新对话
        conv = Conversation(user_id=user_id, title="新对话")
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv


async def _save_message(
    conversation_id: int,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> int:
    """保存消息，返回消息 ID。"""
    async with async_session() as session:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_=metadata,
        )
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        return msg.id


async def _update_message(
    message_id: int,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """更新消息内容（增量持久化用）。"""
    async with async_session() as session:
        result = await session.execute(
            select(Message).where(Message.id == message_id)
        )
        msg = result.scalar_one_or_none()
        if msg:
            msg.content = content
            if metadata is not None:
                msg.metadata_ = metadata
            await session.commit()


# ---------------------------------------------------------------------------
# TripService
# ---------------------------------------------------------------------------

class TripService:
    """行程服务 — 对齐 Node.js TripService。"""

    # ==================== chat_stream ====================

    async def chat_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式对话 + 增量持久化 + 事件生成。

        Yields:
            事件字典（由 create_resumable_stream 包装为 SSE 格式）。
            - {"type": "chunk", "content": "..."}
            - {"type": "tool_start", "name": "..."}
            - {"type": "tool_end", "name": "..."}
            - {"type": "complete", "data": {"conversationId": ..., "usage": ...}}
            - {"type": "error", "error": "..."}
            - {"type": "heartbeat"}

        Note:
            Agent 任务通过 asyncio.shield 保护，客户端断连后 Agent
            继续运行并将 events 写入 StreamStore，支持断点续传。
        """
        # ---- 1. 准备对话 & 持久化用户消息 ----
        conversation = await _get_or_create_conversation(user_id, conversation_id)
        conv_id = conversation.id

        if not conversation.title or conversation.title == "新对话":
            try:
                async with async_session() as session:
                    await auto_title(session, conv_id, message)
            except Exception as e:
                trip_log.warning(err=str(e), msg="auto_title 失败")

        await _save_message(conv_id, "user", message)

        # ---- 1.5 非旅行问题拦截（代码层强制，不依赖 LLM） ----
        non_travel_keywords = [
            "Python", "python", "编程", "代码", "list", "tuple",
            "数学", "历史", "物理", "化学", "娱乐", "新闻",
            "股票", "基金", "显卡", "CPU", "手机", "电脑",
        ]
        travel_keywords = [
            "旅行", "旅游", "出行", "行程", "规划", "攻略",
            "景点", "美食", "酒店", "机票", "火车",
            "去哪儿", "推荐", "安排", "玩", "去哪",
        ]
        msg_lower = message.lower()
        has_travel = any(kw in msg_lower for kw in travel_keywords)
        is_non_travel = any(kw in msg_lower for kw in non_travel_keywords)
        
        if is_non_travel and not has_travel:
            # 非旅行问题，直接返回固定拒绝语，不调用 Agent
            rejection_msg = "抱歉，我是旅行规划助手，只能帮助您解决旅游、出行、行程规划相关的问题。请问您有什么旅游出发目的地的计划需要帮助吗？"
            await _save_message(conv_id, "assistant", rejection_msg)
            yield {"type": "chunk", "content": rejection_msg}
            yield {
                "type": "complete",
                "data": {"conversationId": conv_id, "usage": {"prompt": 0, "completion": 0, "total": 0}}
            }
            return

        # 预创建空 assistant 消息
        assistant_msg_id = await _save_message(conv_id, "assistant", "")

        # ---- 2. 状态变量 ----
        full_reply = ""
        last_persist_at = time.time() * 1000
        persisted = False
        last_usage: Optional[dict] = None
        queue: asyncio.Queue = asyncio.Queue()

        # ---- 3. 增量持久化 ----
        async def persist_assistant(content: str, force: bool = False, usage: Optional[dict] = None):
            nonlocal last_persist_at, persisted
            if persisted:
                return
            if not content:
                return
            now = time.time() * 1000
            if not force and (now - last_persist_at) < ASSISTANT_PERSIST_FLUSH_INTERVAL_MS:
                return
            last_persist_at = now
            metadata = {"usage": usage} if usage else None
            for attempt in range(2):
                try:
                    await _update_message(assistant_msg_id, content, metadata)
                    return
                except Exception as e:
                    if attempt == 0:
                        await asyncio.sleep(0.2)
                        continue
                    trip_log.error(err=str(e), msg="增量持久化失败（重试已耗尽）")

        # ---- 4. Agent 事件回调 ----
        async def on_event(event: dict):
            nonlocal full_reply, persisted, last_usage
            event_type = event.get("type", "")

            if event_type == "chunk":
                chunk = event.get("content", "")
                full_reply += chunk
                await queue.put({"type": "chunk", "content": chunk})
                await persist_assistant(full_reply)

            elif event_type == "tool_start":
                await queue.put({"type": "tool_start", "name": event.get("name", "")})

            elif event_type == "tool_end":
                await queue.put({"type": "tool_end", "name": event.get("name", "")})

            elif event_type == "complete":
                full_reply = event.get("content", full_reply)
                usage = event.get("usage")
                if usage:
                    last_usage = usage
                await persist_assistant(full_reply, force=True, usage=usage)
                persisted = True
                await queue.put({"__done__": True})

            elif event_type == "error":
                await persist_assistant(full_reply, force=True)
                await queue.put({"__error__": True, "error": event.get("error", "未知错误")})

        # ---- 5. 启动 Agent（后台，shield 保护断连后继续运行） ----
        async def run_agent():
            try:
                agent_engine = get_agent_engine()
                await agent_engine.chat(
                    user_id=user_id,
                    message=message,
                    conversation_id=conv_id,
                    message_id=assistant_msg_id,
                    on_event=on_event,
                )
            except asyncio.CancelledError:
                # Shield 保护：客户端断连时 shield 向内部发送 CancelledError
                trip_log.info("Agent shield-cancelled (client disconnect)")
            except Exception as e:
                await queue.put({"__error__": True, "error": str(e)})

        # shield 确保客户端断连后 Agent 继续运行，events 写入 StreamStore
        agent_task = asyncio.shield(run_agent())

        # ---- 6. 心跳 + 事件循环 ----
        heartbeat_interval = 15  # 秒
        last_heartbeat = time.time()

        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if time.time() - last_heartbeat >= heartbeat_interval:
                        yield {"type": "heartbeat"}
                        last_heartbeat = time.time()
                    continue

                # 结束标记
                if event.get("__done__"):
                    self._post_chat_tasks(conv_id, message)
                    yield {
                        "type": "complete",
                        "data": {"conversationId": conv_id, "usage": last_usage},
                    }
                    break

                # 错误标记
                if event.get("__error__"):
                    self._post_chat_tasks(conv_id, message)
                    yield {"type": "error", "error": event.get("error", "未知错误")}
                    break

                # 正常事件（delta / tool_start / tool_end）
                yield event
                last_heartbeat = time.time()

        except asyncio.CancelledError:
            # 客户端断连 → 强制持久化已有内容
            # Agent 任务因 shield 保护继续运行，events 写入 StreamStore 支持续传
            if not persisted and full_reply:
                await persist_assistant(full_reply, force=True)
            raise
        finally:
            # 不取消 agent_task（shield 保护它继续运行）
            pass

    def _post_chat_tasks(self, conversation_id: int, user_message: str) -> None:
        """对话结束后异步任务：压缩 + 关键决策记录。"""

        async def _run():
            # 压缩
            try:
                async with async_session() as session:
                    await summary_service.compress_conversation(session, conversation_id)
            except Exception as e:
                trip_log.warning(err=str(e), conversationId=conversation_id, msg="摘要压缩失败")

            # 关键决策
            if is_planning_request(user_message):
                decision = f"用户发起行程规划：{user_message}"
                try:
                    async with async_session() as session:
                        await summary_service.append_key_decision(session, conversation_id, decision)
                except Exception as e:
                    trip_log.warning(err=str(e), conversationId=conversation_id, msg="记录关键决策失败")

        asyncio.create_task(_run())

    # ==================== recommend ====================

    async def recommend(
        self,
        city: str,
        budget: int,
        days: int,
        user_id: Optional[int] = None,
        departure_city: Optional[str] = None,
    ) -> dict:
        """行程推荐。

        Args:
            city: 目标城市
            budget: 预算（元）
            days: 天数
            user_id: 用户 ID
            departure_city: 出发城市

        Returns:
            完整行程推荐结果字典
        """
        _t0 = time.time()
        if budget < 50 or budget > 1_000_000 or days < 1 or days > 30:
            raise ValueError("预算或天数不符合要求（预算范围 50-1,000,000，天数 1-30）")

        try:
            agent_engine = get_agent_engine()
            result = await agent_engine.recommend(
                user_id=user_id or 0,
                city=city,
                budget=budget,
                days=days,
                departure_city=departure_city,
            )
            _t_agent = time.time()
            logger.info("recommend|agent_engine=%dms city=%s days=%d budget=%d",
                        int((_t_agent - _t0) * 1000), city, days, budget)

            parsed = result.get("parsed")
            if not parsed:
                raise ValueError("Agent 返回无效结果")

            # ---- geocoding + 图片增强（best-effort，并行执行） ----
            await asyncio.gather(
                self._enrich_geocoding(parsed),
                self._enrich_images(parsed),
                return_exceptions=True,
            )
            _t_enrich = time.time()

            # ---- 持久化 Trip（后台异步，不阻塞响应） ----
            # 注意：parsed 已在 enrich 阶段完成修改，后台任务持有引用不会丢失
            asyncio.create_task(_persist_trip_background(
                user_id=user_id,
                from_city=departure_city,
                parsed=parsed,
                budget=budget,
            ))

            _t_total = time.time()
            logger.info(
                "recommend|total=%dms agent=%dms enrich=%dms city=%s days=%d budget=%d",
                int((_t_total - _t0) * 1000),
                int((_t_agent - _t0) * 1000),
                int((_t_total - _t_agent) * 1000),
                city, days, budget,
            )

            return {
                "success": True,
                "data": {
                    "id": None,  # 后台异步持久化，不等待 DB 写入
                    "city": parsed.get("city", city),
                    "days": parsed.get("days", days),
                    "totalBudget": parsed.get("totalBudget"),
                    "dailyItinerary": parsed.get("dailyItinerary"),
                    "budgetBreakdown": parsed.get("budgetBreakdown"),
                    "tips": parsed.get("tips"),
                    "warnings": parsed.get("warnings"),
                },
            }
        except Exception as e:
            trip_log.error(err=str(e), msg="行程推荐失败")
            raise ValueError("行程推荐失败，请稍后重试")

    # ---- private helpers ----

    @staticmethod
    async def _enrich_geocoding(parsed: dict) -> None:
        """为景点补充经纬度（best-effort，使用高德 API）。

        如果 geocode 服务未配置，静默跳过。
        """
        try:
            from src.services.geocode_service import enrich_trip_with_geocoding
            await enrich_trip_with_geocoding(parsed)
        except ImportError:
            pass  # geocode_service 尚未实现
        except Exception as e:
            trip_log.warning(err=str(e), msg="geocoding enrichment failed, continuing")

    @staticmethod
    async def _enrich_images(parsed: dict) -> None:
        """为景点补充封面图片 URL（best-effort，Amap MCP 优先 / Unsplash 降级）。

        如果图片服务未配置，静默跳过。
        """
        try:
            from src.services.unsplash_service import enrich_trip_with_images
            await enrich_trip_with_images(parsed)
        except ImportError:
            pass  # unsplash_service 尚未实现
        except Exception as e:
            trip_log.warning(err=str(e), msg="image enrichment failed, continuing")

    @staticmethod
    async def _persist_trip(
        user_id: Optional[int],
        from_city: Optional[str],
        parsed: dict,
        budget: int,
        parent_trip_id: Optional[int] = None,
    ) -> Optional[int]:
        """持久化 Trip 记录到数据库。返回 trip ID。"""
        async with async_session() as session:
            trip = Trip(
                user_id=user_id,
                from_city=from_city,
                city=parsed.get("city", ""),
                days=parsed.get("days", 1),
                budget=budget,
                content=parsed,
                status="completed",
                parent_trip_id=parent_trip_id,
            )
            session.add(trip)
            await session.commit()
            await session.refresh(trip)
            return trip.id


# ---------------------------------------------------------------------------
# 后台持久化（异步，不阻塞响应）
# ---------------------------------------------------------------------------

async def _persist_trip_background(
    user_id: Optional[int],
    from_city: Optional[str],
    parsed: dict,
    budget: int,
    parent_trip_id: Optional[int] = None,
) -> None:
    """后台持久化 Trip 记录（fire-and-forget）。"""
    try:
        async with async_session() as session:
            trip = Trip(
                user_id=user_id,
                from_city=from_city,
                city=parsed.get("city", ""),
                days=parsed.get("days", 1),
                budget=budget,
                content=parsed,
                status="completed",
                parent_trip_id=parent_trip_id,
            )
            session.add(trip)
            await session.commit()
    except Exception as e:
        trip_log.error(err=str(e), msg="recommend|persist_background failed")


# 模块单例
trip_service = TripService()
