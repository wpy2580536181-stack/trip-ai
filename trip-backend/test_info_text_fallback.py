"""Targeted test: chat_agent._execute_tool_card with retrieve_knowledge_tool
returns plain text -> must emit info_text card (NOT silent drop / hang).

Reproduces the user-reported "I want to go shopping" symptom: agent streams
"let me look it up..." but the tool result is never displayed, so user perceives
a freeze. This test directly invokes the card-execution path with a mocked
retrieve_knowledge_tool that returns a text fallback.
"""
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.services.rag.embeddings import mark_embedder_unavailable
mark_embedder_unavailable()

from src.config.llm import create_llm
from src.services.agent.agents.chat_agent import ChatAgent


async def main():
    events = []
    card_events = []

    async def on_event(e):
        events.append(e)
        if e.get("type") == "card":
            card_events.append(e)

    # Build ChatAgent (real LLM, but we won't call run() — just _execute_tool_card)
    llm = create_llm(streaming=True)
    agent = ChatAgent(llm=llm, on_event=on_event, system_prompt="你是旅行助手。", user_id=1)

    # Build a fake retrieve_knowledge_tool that returns PLAIN TEXT (simulates the
    # bug-triggering scenario: with_resilience fallback or formatted string).
    from langchain_core.tools import tool

    @tool
    async def fake_retrieve_knowledge(query: str, city: str, category: str = "") -> str:
        """Fake knowledge retrieval returning Markdown text."""
        return (
            f"# {city} 逛街好去处\n\n"
            "1. **南京路步行街** — 百年老街，购物中心密集\n"
            "2. **淮海路** — 时尚商业街\n"
            "3. **新天地** — 石库门风情+潮流店铺\n"
        )

    fake_retrieve_knowledge.name = "retrieve_knowledge_tool"

    # 注入工具：直接设置 agent.tools
    agent.tools = [fake_retrieve_knowledge]  # LangChain @tool 自动注入 ainvoke / description

    print("[TEST] invoking _execute_tool_card with text-fallback tool", flush=True)
    print(f"[DBG] tool.name = {fake_retrieve_knowledge.name!r}", flush=True)
    print(f"[DBG] agent.tools count = {len(agent.tools)}", flush=True)
    t0 = time.time()
    try:
        result = await agent._execute_tool_card(
            tool_name="retrieve_knowledge_tool",  # 与重命名后的 tool.name 对齐
            args={"query": "逛街 购物 商圈", "city": "上海", "category": "景点"},
            user_msg="我想逛街",
        )
    except Exception as e:
        print(f"[DBG] _execute_tool_card raised: {type(e).__name__}: {e}", flush=True)
        raise
    print(f"[RESULT] elapsed={time.time()-t0:.2f}s result_len={len(result or '')}", flush=True)
    print(f"[RESULT-TEXT-FIRST] {(result or '')[:200]}", flush=True)
    print(f"\n[CARD EVENTS] count={len(card_events)}", flush=True)
    for e in card_events:
        ct = e.get("card_type")
        title = e.get("data", {}).get("title")
        content_preview = (e.get("data", {}).get("content") or "")[:200]
        print(f"  - card_type={ct} title={title!r}", flush=True)
        print(f"    content: {content_preview}...", flush=True)

    # 关键断言：必须有 info_text 卡片，不能默默丢弃
    assert card_events, "FAIL: 没有卡片发出 → 用户仍然看到「让我先查查…」却无下文(卡死感)"
    text_cards = [e for e in card_events if e.get("card_type") == "info_text"]
    assert text_cards, (
        f"FAIL: 没有 info_text 卡片；发出的卡片类型: "
        f"{[e.get('card_type') for e in card_events]}"
    )
    c = text_cards[0]
    data = c.get("data", {})
    assert "南京路" in (data.get("content") or ""), "卡片内容缺少检索结果"
    assert data.get("title"), "info_text 卡片应带标题"

    # 同时验证 _execute_tool_card 把工具结果作为 reply 返回，确保前端万一没渲染卡片
    # 用户也能从消息气泡里看到关键信息（防御性双通道）。
    assert result and "南京路" in result, f"reply 也应包含工具结果；当前: {result!r}"

    print("\n✅ PASS: info_text 卡片正确发出，用户实时看到工具结果。", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
