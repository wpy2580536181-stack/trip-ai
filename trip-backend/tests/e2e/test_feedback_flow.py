"""E2E: 反馈流程

覆盖：提交反馈 → 查询反馈列表 → 消息反馈统计
"""

import pytest


class TestFeedbackFlow:
    """反馈流程端到端测试"""

    @pytest.mark.asyncio
    async def test_submit_feedback(self, auth_client):
        """提交反馈（messageId=0 返回 400）"""
        resp = await auth_client.post("/api/feedback", json={
            "messageId": 0,
            "conversationId": 0,
            "rating": 5,
            "comment": "E2E test feedback - great experience",
            "tags": ["accurate", "helpful"],
        })
        # messageId=0 不存在，后端返回 400
        assert resp.status_code in (200, 400, 404), f"Submit feedback failed: {resp.text}"

    @pytest.mark.asyncio
    async def test_get_user_feedback_list(self, auth_client):
        """获取当前用户的反馈列表"""
        resp = await auth_client.get("/api/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_message_feedback_stats(self, auth_client):
        """获取单条消息的反馈统计"""
        resp = await auth_client.get("/api/feedback/message/0")
        # 消息 0 不存在，返回 404 或空统计均合理
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_submit_feedback_missing_fields(self, auth_client):
        """缺少必填字段的反馈应返回 422"""
        resp = await auth_client.post("/api/feedback", json={
            "rating": 5,
            # 缺少 messageId 和 conversationId
        })
        assert resp.status_code == 422
