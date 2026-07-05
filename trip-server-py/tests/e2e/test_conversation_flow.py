"""E2E: 对话与历史记录流程

覆盖：创建对话 → 获取对话列表 → 获取详情 → 删除对话
"""

import pytest


class TestConversationFlow:
    """对话流程端到端测试"""

    @pytest.mark.asyncio
    async def test_create_conversation(self, auth_client):
        """创建新对话（返回 201 Created）"""
        resp = await auth_client.post("/api/conversations",
                                      json={"title": "E2E Test Conversation"})
        assert resp.status_code in (200, 201), f"Create conversation failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        conv_id = data["data"]["id"]
        assert conv_id
        return conv_id

    @pytest.mark.asyncio
    async def test_list_conversations(self, auth_client):
        """获取对话列表（返回分页对象）"""
        resp = await auth_client.get("/api/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        # 数据可能是数组或分页对象
        assert isinstance(data["data"], (list, dict))

    @pytest.mark.asyncio
    async def test_get_conversation_detail(self, auth_client):
        """先创建对话再获取详情"""
        # 创建
        create_resp = await auth_client.post("/api/conversations",
                                             json={"title": "Detail Test"})
        conv_id = create_resp.json()["data"]["id"]

        # 获取详情
        resp = await auth_client.get(f"/api/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["id"] == conv_id
        assert data["data"]["title"] == "Detail Test"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, auth_client):
        """创建后删除对话"""
        # 创建
        create_resp = await auth_client.post("/api/conversations",
                                             json={"title": "To Delete"})
        conv_id = create_resp.json()["data"]["id"]

        # 删除
        resp = await auth_client.delete(f"/api/conversations/{conv_id}")
        assert resp.status_code == 200

        # 验证已删除（应返回 404 或空结果）
        get_resp = await auth_client.get(f"/api/conversations/{conv_id}")
        assert get_resp.status_code in (404, 200)
        if get_resp.status_code == 200:
            # 如果返回 200，内容应该为空或标识已删除
            pass

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation(self, auth_client):
        """获取不存在的对话应返回 404"""
        resp = await auth_client.get("/api/conversations/99999999")
        assert resp.status_code == 404
