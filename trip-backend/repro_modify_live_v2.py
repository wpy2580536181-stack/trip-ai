"""Faithful live-path repro for "我想逛街" → trigger_modify → Orchestrator.modify.

Mimics what agent_engine.chat() does: full system prompt, conversation history,
trip_context, and on_event SSE callback. Reproduces the user-reported freeze
under controlled conditions.
"""
import asyncio
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

# 让 main / agent modules 可被 import
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config.llm import create_llm
from src.services.agent.agent_engine import AgentEngine
from src.services.agent.system_prompt import build_system_prompt

EXISTING_TRIP = {
    "city": "上海",
    "days": 3,
    "totalBudget": 6000,
    "dailyItinerary": [
        {
            "day": 1, "date": "",
            "morning": {"spot": "外滩", "duration": "2小时", "ticket": "免费", "transportation": "地铁", "description": ""},
            "afternoon": {"spot": "南京路", "duration": "2小时", "ticket": "免费", "transportation": "步行", "description": ""},
            "evening": {"spot": "豫园", "duration": "2小时", "ticket": "40元", "transportation": "地铁", "description": ""},
            "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
            "lunch": {"spot": "南翔馒头店", "duration": "1小时", "ticket": "80元", "transportation": "", "description": ""},
            "dinner": {"spot": "老饭店", "duration": "1小时", "ticket": "150元", "transportation": "", "description": ""},
            "accommodation": {"spot": "外滩附近酒店", "duration": "", "ticket": "600元", "transportation": "", "description": ""},
        },
        {
            "day": 2, "date": "",
            "morning": {"spot": "上海迪士尼乐园", "duration": "4小时", "ticket": "599元", "transportation": "地铁", "description": ""},
            "afternoon": {"spot": "上海迪士尼乐园", "duration": "4小时", "ticket": "", "transportation": "", "description": ""},
            "evening": {"spot": "迪士尼小镇", "duration": "2小时", "ticket": "免费", "transportation": "步行", "description": ""},
            "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
            "lunch": {"spot": "迪士尼宫内餐厅", "duration": "1小时", "ticket": "120元", "transportation": "", "description": ""},
            "dinner": {"spot": "迪士尼小镇餐厅", "duration": "1小时", "ticket": "150元", "transportation": "", "description": ""},
            "accommodation": {"spot": "外滩附近酒店", "duration": "", "ticket": "600元", "transportation": "", "description": ""},
        },
        {
            "day": 3, "date": "",
            "morning": {"spot": "上海博物馆", "duration": "3小时", "ticket": "免费", "transportation": "地铁", "description": ""},
            "afternoon": {"spot": "人民广场", "duration": "1小时", "ticket": "免费", "transportation": "步行", "description": ""},
            "evening": {"spot": "新天地", "duration": "2小时", "ticket": "免费", "transportation": "地铁", "description": ""},
            "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
            "lunch": {"spot": "上海老站", "duration": "1小时", "ticket": "120元", "transportation": "", "description": ""},
            "dinner": {"spot": "新天地餐厅", "duration": "1小时", "ticket": "180元", "transportation": "", "description": ""},
            "accommodation": {"spot": "外滩附近酒店", "duration": "", "ticket": "600元", "transportation": "", "description": ""},
        },
    ],
    "budgetBreakdown": {"accommodation": 1800, "food": 1200, "transportation": 1500, "tickets": 1000, "other": 500},
    "tips": ["带好身份证"],
    "warnings": [],
}


async def main():
    # 强制模拟生产启动：fail-closed + 跳过模型下载
    from src.services.rag.embeddings import mark_embedder_unavailable
    mark_embedder_unavailable()

    engine = AgentEngine()
    # 不再额外启动 warmup，因为已经 fail-closed；预热会再后台重试（与本次单次请求无关）

    events = []
    stage_marks = []  # (abs_time, stage_label)

    async def on_event(e):
        events.append(e)
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] EVENT type={e.get('type')} :: {str(e)[:160]}", flush=True)
        if e.get("type") == "progress" and isinstance(e.get("data"), dict):
            stage = e["data"].get("stage")
            if stage:
                stage_marks.append((time.time(), stage))

    # 复现截图场景：用户提供一个"现有行程"上下文，trip_id 走不通真实 DB（与"我想逛街"无关）
    trip_context = (
        f"用户已有上海3日游行程（预算6000元）。"
        f"第2天安排了迪士尼，用户在对话中提到想换掉。"
        f"完整行程内容：\n```json\n{str(EXISTING_TRIP)[:400]}\n```"
    )

    message = "我想逛街"

    print(f"[START] engine.chat message={message!r}", flush=True)
    t0 = time.time()

    async def watchdog():
        while True:
            await asyncio.sleep(5)
            el = time.time() - t0
            n = len(events)
            last_type = events[-1]["type"] if events else "-"
            print(f"[WATCHDOG] elapsed={el:.1f}s events={n} last={last_type}", flush=True)

    wd = asyncio.create_task(watchdog())
    try:
        result = await asyncio.wait_for(
            engine.chat(
                user_id=1,
                message=message,
                conversation_id=None,
                on_event=on_event,
                trip_context=trip_context,
                trip_id=None,  # 不查 DB，避免外键干扰，专注 chat_agent 主链路
            ),
            timeout=180,
        )
        wd.cancel()
        print(f"[DONE] elapsed={time.time()-t0:.1f}s reply_len={len(result.get('reply') or '')}", flush=True)
        print(f"[REPLY] {(result.get('reply') or '')[:400]}", flush=True)
    except asyncio.TimeoutError:
        wd.cancel()
        print(f"[TIMEOUT] modify flow did NOT return within 180s. Last events:", flush=True)
        for e in events[-20:]:
            print("   ", e.get("type"), str(e)[:120], flush=True)

    print("\n=== STAGE SPANS (秒) ===", flush=True)
    for i in range(1, len(stage_marks)):
        prev_t, prev_s = stage_marks[i - 1]
        cur_t, cur_s = stage_marks[i]
        span = cur_t - prev_t
        flag = "  <-- 偏长" if span > 10 else ""
        print(f"  {prev_s!r} -> {cur_s!r}: {span:.1f}s{flag}", flush=True)
    if stage_marks:
        print(f"  total progress span: {stage_marks[-1][0]-stage_marks[0][0]:.1f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
