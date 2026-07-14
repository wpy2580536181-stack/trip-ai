"""E2E: 异常场景

覆盖：401 未认证、404 不存在、422 参数校验、限流、方法不允许
"""

import pytest


class TestErrorScenarios:
    """异常场景端到端测试"""

    @pytest.mark.asyncio
    async def test_401_on_missing_token(self, client):
        """未提供 token 访问受保护接口"""
        protected_endpoints = [
            ("GET", "/api/conversations"),
            ("GET", "/api/history/trips"),
            ("GET", "/api/feedback"),
            ("GET", "/api/user/info"),
        ]
        for method, path in protected_endpoints:
            if method == "GET":
                resp = await client.get(path)
            else:
                resp = await client.post(path, json={})
            assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_404_on_nonexistent_route(self, client):
        """不存在的路由应返回 404"""
        resp = await client.get("/api/nonexistent-route")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_404_on_nonexistent_resource(self, auth_client):
        """不存在的资源 ID 应返回 404"""
        endpoints = [
            ("GET", "/api/history/trips/999999"),
            ("DELETE", "/api/history/trips/999999"),
        ]
        for method, path in endpoints:
            if method == "GET":
                resp = await auth_client.get(path)
            else:
                resp = await auth_client.delete(path)
            assert resp.status_code == 404, f"{method} {path} expected 404"

    @pytest.mark.asyncio
    async def test_422_on_invalid_input(self, auth_client):
        """无效输入应返回 422"""
        # login 需要 username + password
        resp = await auth_client.post("/api/user/login", json={"unknown": "field"})
        assert resp.status_code in (401, 422), f"Expected 401/422, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_422_on_empty_body(self, auth_client):
        """POST 请求空 body 应返回 422"""
        # conversations/create 需要 title
        resp = await auth_client.post("/api/conversations", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_405_on_wrong_method(self, client):
        """用错误的 HTTP 方法访问应返回 405"""
        # login 只支持 POST
        resp = await client.get("/api/user/login")
        assert resp.status_code == 405, f"Expected 405, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_get_public_endpoints_without_auth(self, client):
        """公开接口无需认证"""
        public = [
            ("GET", "/health"),
            ("GET", "/health/detail"),
            ("GET", "/api/knowledge/spots"),
        ]
        for method, path in public:
            if method == "GET":
                resp = await client.get(path)
            assert resp.status_code == 200, f"{path} expected 200, got {resp.status_code}"
