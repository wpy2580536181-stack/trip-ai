"""临时调试脚本：测试多轮对话路由和 tool call 行为"""
import asyncio
import json
import logging
import httpx

logging.basicConfig(level=logging.WARNING)

BASE_URL = "http://127.0.0.1:8000"
USERNAME = "eval-test"
PASSWORD = "EvalTest@2026"

async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        # 1. Login
        resp = await client.post(f"{BASE_URL}/api/user/login", json={"username": USERNAME, "password": PASSWORD})
        data = resp.json()
        print(f"Login status: {resp.status_code}")
        print(f"Login response: {json.dumps(data, ensure_ascii=False)[:200]}")
        
        token_data = data.get("data", {})
        token = token_data.get("token", "")
        if not token:
            print("Login failed - no token")
            return
        print(f"Token: {token[:30]}...")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 2. First turn
        print("\n=== First turn: 杭州 2 天行程 ===")
        async with client.stream("POST", f"{BASE_URL}/api/trip/chat", json={"message": "杭州 2 天行程"}, headers=headers) as stream:
            text = ""
            tool_starts = []
            conv_id = None
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        evt = json.loads(data_str)
                        etype = evt.get("type", "")
                        if etype == "chunk":
                            text += evt.get("content", "")
                        elif etype == "tool_start":
                            tool_starts.append(evt.get("name", ""))
                        elif etype == "complete":
                            conv_id = evt.get("data", {}).get("conversationId")
                    except json.JSONDecodeError:
                        pass
            print(f"  Tool starts: {tool_starts}")
            print(f"  Conv ID: {conv_id}")
            print(f"  First turn text (first 200): {text[:200]}")

        # 3. Second turn
        print(f"\n=== Second turn (multi-turn) ===")
        async with client.stream("POST", f"{BASE_URL}/api/trip/chat", 
            json={"message": "你刚才 Day 2 推荐的西湖游船具体是哪个码头出发？船票多少钱？", "conversationId": conv_id}, 
            headers=headers) as stream:
            text2 = ""
            tool_starts2 = []
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        evt = json.loads(data_str)
                        etype = evt.get("type", "")
                        if etype == "chunk":
                            text2 += evt.get("content", "")
                        elif etype == "tool_start":
                            tool_starts2.append(evt.get("name", ""))
                        elif etype == "complete":
                            print(f"  COMPLETE event received")
                        elif etype == "error":
                            print(f"  ERROR: {evt}")
                    except json.JSONDecodeError:
                        pass
            print(f"  Second turn tool starts: {tool_starts2}")
            print(f"  Second turn text: {text2[:500]}")
            print(f"  Has '西湖': {'西湖' in text2}")
            print(f"  Has '游船': {'游船' in text2}")
            print(f"  Has '码头': {'码头' in text2}")

if __name__ == "__main__":
    asyncio.run(main())
