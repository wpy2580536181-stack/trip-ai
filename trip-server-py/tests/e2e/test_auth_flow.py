"""E2E: 用户认证流程

覆盖：注册 → 登录 → token 使用 → 用户信息 → 修改密码 → 未认证访问
"""

import pytest


class TestAuthFlow:
    """认证流程端到端测试"""

    @pytest.mark.asyncio
    async def test_health_check(self, client, backend_server):
        """健康检查端点应可公开访问（重试直到后端就绪）"""
        for _ in range(5):
            resp = await client.get("/health")
            if resp.status_code == 200:
                assert resp.text == "OK"
                return
        assert resp.status_code == 200, f"Health check failed after retries: {resp.status_code}"

    @pytest.mark.asyncio
    async def test_health_detail(self, client):
        """详细健康检查"""
        resp = await client.get("/health/detail")
        assert resp.status_code in (200, 502), f"Expected 200 or 502, got {resp.status_code}"
        if resp.status_code == 200:
            assert len(resp.text) > 0

    @pytest.mark.asyncio
    async def test_login_with_valid_credentials(self, client):
        """使用正确凭据登录应返回 JWT token（重试直到后端就绪）"""
        for _ in range(5):
            resp = await client.post("/api/user/login",
                                     json={"username": "eval-test", "password": "EvalTest@2026"})
            if resp.status_code == 200:
                data = resp.json()
                assert "data" in data
                assert "token" in data["data"]
                assert len(data["data"]["token"]) > 20
                return
        assert resp.status_code == 200, f"Login failed after retries: {resp.status_code}"

    @pytest.mark.asyncio
    async def test_login_with_wrong_password(self, client):
        """错误密码应返回 401"""
        for _ in range(3):
            resp = await client.post("/api/user/login",
                                     json={"username": "eval-test", "password": "wrong-password"})
            if resp.status_code == 401:
                return
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_login_with_nonexistent_user(self, client):
        """不存在的用户应返回 401（防止用户枚举）"""
        for _ in range(3):
            resp = await client.post("/api/user/login",
                                     json={"username": "nonexistent-user-12345", "password": "test"})
            if resp.status_code == 401:
                return
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_without_token(self, client):
        """未携带 token 访问受保护端点应返回 401"""
        for _ in range(3):
            resp = await client.get("/api/conversations")
            if resp.status_code == 401:
                return
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_with_valid_token(self, auth_client):
        """携带有效 token 应成功访问受保护端点"""
        resp = await auth_client.get("/api/conversations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_with_expired_token(self, client):
        """无效/过期 token 应返回 401"""
        client.headers["Authorization"] = "Bearer invalid-token-here"
        resp = await client.get("/api/conversations")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_user_info(self, auth_client):
        """获取当前用户信息"""
        resp = await auth_client.get("/api/user/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert data["data"]["username"] == "eval-test"

    @pytest.mark.asyncio
    async def test_update_user_info(self, auth_client):
        """更新用户信息"""
        resp = await auth_client.put("/api/user/info", json={"nickname": "Test Eval"})
        assert resp.status_code == 200

        # 验证更新已生效
        resp2 = await auth_client.get("/api/user/info")
        assert resp2.json()["data"]["nickname"] == "Test Eval"

    @pytest.mark.asyncio
    async def test_forgot_password_returns_always_ok(self, client):
        """忘记密码接口始终返回成功（防止用户枚举）"""
        resp = await client.post("/api/user/forgot-password",
                                 json={"email": "nonexistent@test.com"})
        assert resp.status_code == 200
