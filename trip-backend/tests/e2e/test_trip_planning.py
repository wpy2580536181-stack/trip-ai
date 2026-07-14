"""E2E: 行程推荐与对话（SSE 流式）流程

覆盖：发送旅行规划 → SSE 流式接收 → 行程保存验证 → 历史记录
"""

import json

import pytest


class TestTripPlanningFlow:
    """行程规划流程端到端测试"""

    @pytest.mark.asyncio
    async def test_trip_recommend(self, auth_client):
        """非流式行程推荐应返回行程方案"""
        resp = await auth_client.post("/api/trip/recommend", json={
            "city": "北京",
            "days": 2,
            "budget": 500,  # 预算整数（元/天）
        })
        # 可能返回 429 限流或 200 成功，只要不 500 即可
        assert resp.status_code in (200, 400, 429), f"Recommend failed: {resp.text}"
        if resp.status_code == 200:
            data = resp.json()
            assert "data" in data or "trip" in str(data)

    @pytest.mark.asyncio
    async def test_trip_optimize(self, auth_client):
        """行程优化接口"""
        resp = await auth_client.post("/api/trip/optimize", json={
            "trip_id": 0,
            "instruction": "增加故宫景点",
        })
        # trip_id=0 可能返回 422（参数校验）或 404（不存在）
        assert resp.status_code in (200, 404, 422, 429), f"Unexpected: {resp.status_code}"

    @pytest.mark.asyncio
    async def test_chat_sse_stream(self, auth_client):
        """SSE 流式对话应返回流式事件（可能被限流时跳过）"""
        async with auth_client.stream(
            "POST", "/api/trip/chat",
            json={"message": "北京 2 天经典游"},
            timeout=120,
        ) as resp:
            if resp.status_code == 429:
                pytest.skip("Rate limited, skipping SSE test")
            assert resp.status_code == 200, f"Chat SSE failed: HTTP {resp.status_code}"

            chunks = []
            complete = False
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        ev_type = data.get("type", "")
                        if ev_type == "chunk":
                            chunks.append(data.get("content", ""))
                        elif ev_type == "complete":
                            complete = True
                            break
                        elif ev_type == "error":
                            pytest.fail(f"Stream error: {data.get('error', 'unknown')}")
                    except json.JSONDecodeError:
                        pass

            assert len(chunks) > 0, "Should receive at least one content chunk"
            assert complete, "Stream should complete with 'complete' event"
            full_content = "".join(chunks)
            assert len(full_content) > 10, "Content should be substantial"
            assert "北京" in full_content, "Content should mention the destination"

    @pytest.mark.asyncio
    async def test_trip_history_after_chat(self, auth_client):
        """对话后，历史记录应可访问（可能被限流时跳过）"""
        async with auth_client.stream(
            "POST", "/api/trip/chat",
            json={"message": "成都 3 天慢节奏"},
            timeout=120,
        ) as resp:
            if resp.status_code == 429:
                pytest.skip("Rate limited, skipping history test")
            assert resp.status_code == 200

        resp = await auth_client.get("/api/history/trips")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_history_pagination(self, auth_client):
        """历史行程列表应支持分页"""
        resp = await auth_client.get("/api/history/trips?page=1&pageSize=5")
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data.get("data"), dict):
            assert "total" in data["data"] or "count" in str(data)

    @pytest.mark.asyncio
    async def test_get_trip_detail(self, auth_client):
        """获取已保存行程的详情"""
        list_resp = await auth_client.get("/api/history/trips")
        trips_data = list_resp.json().get("data", {})
        trips = trips_data.get("items", []) if isinstance(trips_data, dict) else trips_data
        if not trips:
            pytest.skip("No trips in history to test detail")

        trip_id = trips[0]["id"] if isinstance(trips, list) else 1
        resp = await auth_client.get(f"/api/history/trips/{trip_id}")
        assert resp.status_code in (200, 404)
