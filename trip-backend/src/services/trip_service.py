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
        trip_id: Optional[int] = None,
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

            elif event_type in ("trip_modified", "trip_planned", "trip_diff"):
                # 行程状态变更结构化事件：透传给前端（先于 complete 入队）
                await queue.put({"type": event_type, "data": event.get("data")})

            elif event_type == "progress":
                # 阶段进度事件：透传给前端（用于进度条展示）
                await queue.put({"type": "progress", "data": event.get("data")})

            elif event_type == "card":
                # 结构化卡片事件：透传给前端（POI/通勤/Diff 卡片）
                await queue.put({
                    "type": "card",
                    "card_type": event.get("card_type"),
                    "data": event.get("data"),
                })

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
        # 加载行程上下文（trip_id 贯穿）
        trip_context = None
        if trip_id:
            trip_context = await self._build_trip_context(trip_id, user_id)

        async def run_agent():
            try:
                agent_engine = get_agent_engine()
                await agent_engine.chat(
                    user_id=user_id,
                    message=message,
                    conversation_id=conv_id,
                    message_id=assistant_msg_id,
                    on_event=on_event,
                    trip_context=trip_context,
                    trip_id=trip_id,
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
                    await self._post_chat_tasks(conv_id, message)
                    yield {
                        "type": "complete",
                        "data": {"conversationId": conv_id, "usage": last_usage},
                    }
                    break

                # 错误标记
                if event.get("__error__"):
                    await self._post_chat_tasks(conv_id, message)
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

    async def _post_chat_tasks(self, conversation_id: int, user_message: str) -> None:
        """对话结束后异步后处理：入队 post_chat_followup（M2 改造）。

        原实现（M0 之前）：用 `asyncio.create_task(_run())` 启动后台任务。
        问题：FastAPI worker 进程崩溃（OOM / 部署重启 / SIGKILL）任务蒸发，
        对话摘要没压、关键决策没记，没有任何重试 / 状态查询 / 告警。

        改造（决策文档 §3.2 / M2）：改为入队。
        - API 流式响应结束后立即入队（< 5ms 入队）
        - arq worker 异步消费，失败重试 + 死信告警
        - 幂等键 `post_chat:followup:{conversation_id}` —— 同一对话多次流式结束
          （客户端重连 / 续传）只执行 1 次
        """
        try:
            from src.services.task_queue import get_task_queue
            from src.services.tasks.post_chat import post_chat_followup

            # 在 API 端预计算 is_planning_request（避免 worker 内再 import router 链路）
            is_planning = is_planning_request(user_message)

            await get_task_queue().enqueue(
                post_chat_followup,
                conversation_id=conversation_id,
                user_message=user_message,
                is_planning=is_planning,
                job_id=f"post_chat:followup:{conversation_id}",
            )
            trip_log.info(
                "post_chat_followup enqueued",
                conversationId=conversation_id,
                is_planning=is_planning,
            )
        except Exception as e:
            # 入队失败也不抛——不能让流式响应报错
            # 业务损失：对话摘要未压缩、关键决策未记录（可通过 conversations 表
            # 后续手动对账补回）
            trip_log.warning(
                "post_chat_followup_enqueue_failed",
                err=str(e),
                conversationId=conversation_id,
            )

    # ==================== recommend ====================

    async def recommend(
        self,
        city: str,
        budget: int,
        days: int,
        user_id: Optional[int] = None,
        departure_city: Optional[str] = None,
        on_event: Optional[Any] = None,
    ) -> dict:
        """行程推荐。

        Args:
            city: 目标城市
            budget: 预算（元）
            days: 天数
            user_id: 用户 ID
            departure_city: 出发城市
            on_event: 事件回调（progress/tool_start/tool_end，供 SSE 透传，可选）

        Returns:
            完整行程推荐结果字典
        """
        _t0 = time.time()
        if budget < 50 or budget > 1_000_000 or days < 1 or days > 30:
            raise ValueError("预算或天数不符合要求（预算范围 50-1,000,000，天数 1-30）")

        async def _emit(stage: str, status: str) -> None:
            if not on_event:
                return
            try:
                await on_event({"type": "progress", "data": {"stage": stage, "status": status}})
            except Exception:
                pass

        try:
            agent_engine = get_agent_engine()
            result = await agent_engine.recommend_variants(
                user_id=user_id or 0,
                city=city,
                budget=budget,
                days=days,
                departure_city=departure_city,
                on_event=on_event,
            )
            _t_agent = time.time()
            logger.info("recommend|agent_engine=%dms city=%s days=%d budget=%d",
                        int((_t_agent - _t0) * 1000), city, days, budget)

            parsed_variants = result.get("parsed_variants", [])
            if not parsed_variants:
                raise ValueError("Agent 返回无效结果")

            # ---- 持久化每个 variant ----
            await _emit("save", "start")
            variant_summaries: list[dict] = []
            primary: Optional[dict] = None
            primary_plan: dict = {}
            for v in parsed_variants:
                plan = v.get("plan")
                if not plan:
                    # 生成失败的 variant：保留占位（前端展示失败态，不持久化）
                    variant_summaries.append(self._build_variant_summary(v, None))
                    continue
                trip_id = await self._persist_trip(
                    user_id=user_id,
                    from_city=departure_city,
                    parsed=plan,
                    budget=budget,
                    status="candidate",
                )
                summary = self._build_variant_summary(v, trip_id)
                variant_summaries.append(summary)
                if primary is None:
                    primary = summary
                    primary_plan = plan
            await _emit("save", "done")

            _t_total = time.time()
            logger.info(
                "recommend|total=%dms agent=%dms save=%dms city=%s days=%d budget=%d variants=%d",
                int((_t_total - _t0) * 1000),
                int((_t_agent - _t0) * 1000),
                int((_t_total - _t_agent) * 1000),
                city, days, budget, len(variant_summaries),
            )

            return {
                "success": True,
                "data": {
                    "id": primary["tripId"] if primary else None,
                    "city": primary_plan.get("city", city),
                    "days": primary_plan.get("days", days),
                    "totalBudget": primary_plan.get("totalBudget", budget),
                    "dailyItinerary": primary_plan.get("dailyItinerary", []),
                    "budgetBreakdown": primary_plan.get("budgetBreakdown", {}),
                    "tips": primary_plan.get("tips", []),
                    "warnings": primary_plan.get("warnings", []),
                    "variants": variant_summaries,
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
    def _validate_and_fix_trip_data(
        parsed: dict,
        food_spot_names: Optional[set[str]] = None,
    ) -> None:
        """校验并修复行程数据中的常见问题（best-effort）。

        1. accommodation.spot 非住宿类时，尝试清空或置空，防止在地图上显示为餐饮
        2. morning/afternoon/evening 时段禁止填入餐饮，发现则清空
        3. 跨天去重：同一景点只能出现一次，后续重复出现的清空

        Args:
            parsed: 解析后的行程数据
            food_spot_names: 候选池中的餐饮名称集合（用于精确检测）
        """
        _HOTEL_KEYWORDS = ("酒店", "旅馆", "民宿", "宾馆", "公寓", "旅舍", "motel", "hotel", "inn", "resort", "饭店")
        # 餐饮关键词：先检查品牌，再检查类型词（类型词需排除酒店场景）
        _FOOD_BRANDS = (
            "全聚德", "东来顺", "海底捞", "呷哺", "鼎泰丰", "大董", "便宜坊",
            "肯德基", "麦当劳", "星巴克", "喜茶", "奈雪", "蜜雪冰城",
        )
        _FOOD_TYPE_KEYWORDS = ("烤鸭", "餐厅", "餐馆", "火锅", "小吃", "面", "菜", "食", "茶", "咖啡", "bar", "cafe", "restaurant")
        # "饭店"是歧义词（可能是酒店也可能是餐厅），仅当同时包含明确餐饮词时才视为餐饮

        daily_itinerary = parsed.get("dailyItinerary", [])
        if not daily_itinerary:
            return

        # 合并关键词检测和候选池检测
        def _is_food_spot(spot_name: str) -> bool:
            """判断是否为餐饮类地点。"""
            lower = spot_name.lower()
            # 1. 品牌名精确匹配（优先级最高）
            if any(brand in lower for brand in _FOOD_BRANDS):
                return True
            # 2. 类型词匹配（需排除同时包含酒店关键词的歧义场景）
            if any(kw in lower for kw in _FOOD_TYPE_KEYWORDS):
                # "饭店"是歧义词：如果同时包含酒店关键词，则不是餐饮
                if "饭店" in lower and any(hk in lower for hk in _HOTEL_KEYWORDS):
                    return False
                return True
            # 3. 候选池精确匹配
            if food_spot_names and spot_name in food_spot_names:
                return True
            return False

        # 第一轮：检查 accommodation 字段（现有逻辑）
        for day in daily_itinerary:
            slot = day.get("accommodation")
            if not slot or not slot.get("spot"):
                continue
            spot_name = slot["spot"]
            lower = spot_name.lower()
            is_hotel = any(kw in lower for kw in _HOTEL_KEYWORDS)
            is_food = _is_food_spot(spot_name)
            if is_food and not is_hotel:
                trip_log.warning(
                    "accommodation_spot_mismatch",
                    day=day.get("day"),
                    spot=spot_name,
                    action="cleared",
                )
                slot["spot"] = ""
                slot["duration"] = ""
                slot["ticket"] = ""
                slot["transportation"] = ""
                slot["description"] = "住宿信息待确认"

        # 第二轮：检查 morning/afternoon/evening 时段（新增）
        # 2a. 时段餐饮检测 + 跨天去重
        spot_usage: dict[str, list[int]] = {}  # spot_name -> [day1, day2, ...]
        for day in daily_itinerary:
            day_num = day.get("day", 0)
            for period in ("morning", "afternoon", "evening"):
                slot = day.get(period)
                if not slot or not slot.get("spot"):
                    continue
                spot_name = slot["spot"]
                lower = spot_name.lower()

                # 检查是否为餐饮进入景点时段
                is_food = _is_food_spot(spot_name)
                if is_food:
                    trip_log.warning(
                        "food_in_attraction_slot",
                        day=day_num, period=period, spot=spot_name,
                        action="cleared"
                    )
                    slot["spot"] = ""
                    slot["duration"] = ""
                    slot["ticket"] = ""
                    slot["transportation"] = ""
                    slot["description"] = "景点信息待确认"
                    continue

                # 跨天去重检查
                if spot_name in spot_usage:
                    spot_usage[spot_name].append(day_num)
                    trip_log.warning(
                        "duplicate_spot_across_days",
                        spot=spot_name, days=spot_usage[spot_name],
                        action="cleared_later"
                    )
                    # 清空后续重复出现的该景点
                    slot["spot"] = ""
                    slot["duration"] = ""
                    slot["ticket"] = ""
                    slot["transportation"] = ""
                    slot["description"] = "景点信息待确认"
                else:
                    spot_usage[spot_name] = [day_num]

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
        status: str = "completed",
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
                status=status,
                parent_trip_id=parent_trip_id,
            )
            session.add(trip)
            await session.commit()
            await session.refresh(trip)
            return trip.id

    @staticmethod
    def _build_variant_summary(variant_result: dict, trip_id: Optional[int]) -> dict:
        """从 VariantResult 提取前端对比卡片需要的摘要字段。

        Args:
            variant_result: AgentEngine.recommend_variants 返回的 variant dict
            trip_id: 持久化后的 trip ID；生成失败时为 None（前端展示失败态）

        Returns:
            摘要字典，包含 variantType / label / tripId / totalBudget / spotCount /
            highlights / tips；失败时额外带 error 字段
        """
        plan = variant_result.get("plan") or {}
        daily = plan.get("dailyItinerary", [])

        spot_count = 0
        for day in daily:
            for period in ("morning", "afternoon", "evening"):
                slot = day.get(period)
                if slot and slot.get("spot"):
                    spot_count += 1

        highlights = []
        for day in daily[:2]:
            slot = day.get("morning")
            if slot and slot.get("spot"):
                highlights.append(slot["spot"])

        summary = {
            "variantType": variant_result.get("variant_type", ""),
            "label": variant_result.get("label", ""),
            "tripId": trip_id,
            "totalBudget": plan.get("totalBudget", 0),
            "spotCount": spot_count,
            "highlights": highlights[:3],
            "tips": (plan.get("tips") or [])[:2],
        }
        if trip_id is None:
            summary["error"] = variant_result.get("error") or "方案生成失败"
        return summary

    @staticmethod
    async def _build_trip_context(trip_id: int, user_id: int) -> Optional[str]:
        """加载行程摘要（精简文本，控制 token 消耗）。

        Args:
            trip_id: 行程 ID
            user_id: 用户 ID（校验归属）

        Returns:
            行程摘要文本，加载失败时返回 None
        """
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
                )
                trip = result.scalar_one_or_none()
                if not trip or not trip.content:
                    return None

                content = trip.content
                lines = []
                lines.append(
                    f"[trip_id={trip.id}] {content.get('city', trip.city)} "
                    f"{content.get('days', trip.days)}日游 "
                    f"预算{content.get('totalBudget', trip.budget)}元"
                )

                # 每日景点摘要
                for day in (content.get("dailyItinerary") or []):
                    day_num = day.get("day", "?")
                    spots = []
                    for period in ("morning", "afternoon", "evening"):
                        slot = day.get(period)
                        if slot and slot.get("spot"):
                            name = slot["spot"]
                            lat = slot.get("latitude")
                            lng = slot.get("longitude")
                            if lat and lng:
                                spots.append(f"{name}({lat},{lng})")
                            else:
                                spots.append(name)
                    meals = []
                    for meal in ("lunch", "dinner"):
                        slot = day.get(meal)
                        if slot and slot.get("spot"):
                            meals.append(f"{meal}:{slot['spot']}")
                    line = f"Day{day_num}: {' → '.join(spots)}"
                    if meals:
                        line += f" | {' '.join(meals)}"
                    lines.append(line)

                # 预算明细
                bd = content.get("budgetBreakdown")
                if bd:
                    lines.append(
                        f"预算: 住宿{bd.get('accommodation', 0)}/"
                        f"餐饮{bd.get('food', 0)}/"
                        f"交通{bd.get('transportation', 0)}/"
                        f"门票{bd.get('tickets', 0)}/"
                        f"其他{bd.get('other', 0)}"
                    )

                return "\n".join(lines)
        except Exception as e:
            trip_log.warning(err=str(e), msg="build_trip_context failed")
            return None


# 模块单例
trip_service = TripService()
