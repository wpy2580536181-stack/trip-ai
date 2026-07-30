"""Reproduce the live modify flow: chat_agent.run(message) -> trigger_modify -> Orchestrator.modify.
Captures every SSE event with timestamps + a watchdog to locate the stall point.
"""
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

from src.config.llm import create_llm
from src.services.agent.agents.chat_agent import ChatAgent

EXISTING_TRIP = {
    "city": "上海",
    "days": 3,
    "totalBudget": 6000,
    "dailyItinerary": [
        {
            "day": 1, "date": "",
            "morning": {"spot": "外滩", "duration": "2小时", "ticket": "免费", "transportation": "地铁", "description": "看万国建筑"},
            "afternoon": {"spot": "南京路", "duration": "2小时", "ticket": "免费", "transportation": "步行", "description": "购物步行街"},
            "evening": {"spot": "豫园", "duration": "2小时", "ticket": "40元", "transportation": "地铁", "description": "老城厢"},
            "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
            "lunch": {"spot": "南翔馒头店", "duration": "1小时", "ticket": "80元", "transportation": "", "description": "小笼包"},
            "dinner": {"spot": "老饭店", "duration": "1小时", "ticket": "150元", "transportation": "", "description": "本帮菜"},
            "accommodation": {"spot": "外滩附近酒店", "duration": "", "ticket": "600元", "transportation": "", "description": "江景"},
        },
        {
            "day": 2, "date": "",
            "morning": {"spot": "上海迪士尼乐园", "duration": "4小时", "ticket": "599元", "transportation": "地铁", "description": "亲子游"},
            "afternoon": {"spot": "上海迪士尼乐园", "duration": "4小时", "ticket": "", "transportation": "", "description": "继续玩"},
            "evening": {"spot": "迪士尼小镇", "duration": "2小时", "ticket": "免费", "transportation": "步行", "description": "晚餐"},
            "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
            "lunch": {"spot": "迪士尼宫内餐厅", "duration": "1小时", "ticket": "120元", "transportation": "", "description": ""},
            "dinner": {"spot": "迪士尼小镇餐厅", "duration": "1小时", "ticket": "150元", "transportation": "", "description": ""},
            "accommodation": {"spot": "外滩附近酒店", "duration": "", "ticket": "600元", "transportation": "", "description": "江景"},
        },
        {
            "day": 3, "date": "",
            "morning": {"spot": "上海博物馆", "duration": "3小时", "ticket": "免费", "transportation": "地铁", "description": "文物"},
            "afternoon": {"spot": "人民广场", "duration": "1小时", "ticket": "免费", "transportation": "步行", "description": ""},
            "evening": {"spot": "新天地", "duration": "2小时", "ticket": "免费", "transportation": "地铁", "description": "时尚区"},
            "breakfast": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
            "lunch": {"spot": "上海老站", "duration": "1小时", "ticket": "120元", "transportation": "", "description": ""},
            "dinner": {"spot": "新天地餐厅", "duration": "1小时", "ticket": "180元", "transportation": "", "description": ""},
            "accommodation": {"spot": "外滩附近酒店", "duration": "", "ticket": "600元", "transportation": "", "description": "江景"},
        },
    ],
    "budgetBreakdown": {"accommodation": 1800, "food": 1200, "transportation": 1500, "tickets": 1000, "other": 500},
    "tips": ["带好身份证"],
    "warnings": [],
}


async def main():
    # 模拟生产启动时的 fail-closed：默认假设向量模型不可用，避免首请求卡在下载。
    from src.services.rag.embeddings import mark_embedder_unavailable
    mark_embedder_unavailable()

    llm = create_llm(streaming=True)
    events = []
    stage_marks = []  # (abs_time, stage_label)

    async def on_event(e):
        events.append(e)
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] EVENT {e.get('type')} :: {str(e)[:160]}", flush=True)
        if e.get("type") == "progress" and isinstance(e.get("data"), dict):
            stage = e["data"].get("stage")
            if stage:
                stage_marks.append((time.time(), stage))

    trip_meta = {
        "trip_id": 12345,
        "user_id": 1,
        "city": "上海",
        "days": 3,
        "budget": 6000,
        "departure_city": None,
        "content": EXISTING_TRIP,
    }

    agent = ChatAgent(llm=llm, on_event=on_event, system_prompt="你是旅行助手。", user_id=1)
    message = "我第二天不想去迪士尼，换个博物馆或者别的景点吧"

    print(f"[START] chat_agent.run message={message!r}", flush=True)
    t0 = time.time()

    async def watchdog():
        while True:
            await asyncio.sleep(5)
            el = time.time() - t0
            print(f"[WATCHDOG] elapsed {el:.1f}s, events so far: {len(events)}", flush=True)

    wd = asyncio.create_task(watchdog())
    try:
        result = await asyncio.wait_for(
            agent.run(message=message, trip_meta=trip_meta, user_id=1),
            timeout=240,
        )
        wd.cancel()
        print(f"[DONE] elapsed={time.time()-t0:.1f}s result.error={result.error!r} "
              f"result_len={len(result.result) if result.result else 0}", flush=True)
        print(f"[RESULT] {str(result.result)[:400]}", flush=True)
    except asyncio.TimeoutError:
        wd.cancel()
        print(f"[TIMEOUT-HANG] modify flow did NOT return within 240s. Last events:", flush=True)
        for e in events[-15:]:
            print("   ", e.get("type"), str(e)[:120], flush=True)

    # 计算各阶段耗时（取相邻 progress 事件的时间差，反映「卡在哪一步」）。
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
