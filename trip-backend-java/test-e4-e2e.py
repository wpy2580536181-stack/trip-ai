#!/usr/bin/env python3
"""
E4 端到端测试 - Java 后端验证脚本

复用 Python 版 e2e 测试逻辑，指向 Java 后端（端口 8000）
"""

import asyncio
import httpx
import json
import sys
from typing import Optional

# 配置
JAVA_BACKEND_URL = "http://localhost:8000"
E2E_USERNAME = "eval-test"
E2E_PASSWORD = "EvalTest@2026"


class E2ETestRunner:
    def __init__(self):
        self.base_url = JAVA_BACKEND_URL
        self.auth_token: Optional[str] = None
        self.client: Optional[httpx.AsyncClient] = None
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    async def setup(self):
        """初始化客户端并登录"""
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

        # 登录获取 token
        resp = await self.client.post("/api/user/login", json={
            "username": E2E_USERNAME,
            "password": E2E_PASSWORD
        })

        if resp.status_code == 200:
            data = resp.json()
            self.auth_token = data.get("data", {}).get("token")
            print(f"✅ 登录成功，获取 token（前20字符）: {self.auth_token[:20]}...")
        else:
            print(f"❌ 登录失败: {resp.status_code} - {resp.text}")
            sys.exit(1)

    async def teardown(self):
        """清理资源"""
        if self.client:
            await self.client.aclose()

    def get_auth_headers(self) -> dict:
        """获取认证头"""
        if not self.auth_token:
            return {}
        return {"Authorization": f"Bearer {self.auth_token}"}

    async def run_test(self, name: str, test_func):
        """运行单个测试"""
        try:
            await test_func()
            self.passed += 1
            print(f"✅ {name}")
        except AssertionError as e:
            self.failed += 1
            print(f"❌ {name}: {e}")
        except Exception as e:
            self.failed += 1
            print(f"❌ {name}: {type(e).__name__}: {e}")

    async def test_health_check(self):
        """健康检查"""
        resp = await self.client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.text == "OK", f"Expected 'OK', got '{resp.text}'"

    async def test_health_detail(self):
        """详细健康检查"""
        resp = await self.client.get("/health/detail")
        assert resp.status_code in (200, 502), f"Expected 200 or 502, got {resp.status_code}"

    async def test_login_with_valid_credentials(self):
        """使用正确凭据登录"""
        # 已提前登录，仅验证响应格式
        resp = await self.client.post("/api/user/login", json={
            "username": E2E_USERNAME,
            "password": E2E_PASSWORD
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "data" in data, f"Missing 'data' in response: {data}"
        assert "token" in data["data"], f"Missing 'token' in response data: {data['data']}"

    async def test_login_with_wrong_password(self):
        """错误密码应返回 401"""
        resp = await self.client.post("/api/user/login", json={
            "username": E2E_USERNAME,
            "password": "wrong-password"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    async def test_login_with_nonexistent_user(self):
        """不存在的用户应返回 401"""
        resp = await self.client.post("/api/user/login", json={
            "username": "nonexistent-user-12345",
            "password": "test"
        })
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    async def test_access_protected_endpoint_without_token(self):
        """未携带 token 访问受保护端点应返回 401"""
        # 创建无 token 客户端
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
            resp = await client.get("/api/conversations")
            assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"

    async def test_access_protected_endpoint_with_valid_token(self):
        """携带有效 token 应成功访问"""
        resp = await self.client.get("/api/conversations", headers=self.get_auth_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    async def test_get_user_info(self):
        """获取当前用户信息"""
        resp = await self.client.get("/api/user/info", headers=self.get_auth_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "data" in data, f"Missing 'data' in response: {data}"
        assert data["data"]["username"] == E2E_USERNAME, f"Username mismatch: {data['data']['username']}"

    async def test_get_conversations(self):
        """获取会话列表"""
        resp = await self.client.get("/api/conversations", headers=self.get_auth_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "data" in data, f"Missing 'data' in response: {data}"
        # 验证分页字段
        conv_data = data["data"]
        assert "items" in conv_data or isinstance(conv_data, list), "Missing 'items' or list structure"

    async def test_chat_sse_stream(self):
        """SSE 流式对话（简化版 - 只验证流可建立并收到 chunk/complete）"""
        async with self.client.stream(
            "POST",
            "/api/trip/chat",
            json={"message": "北京 2 天经典游"},
            headers=self.get_auth_headers(),
            timeout=120,
        ) as resp:
            if resp.status_code == 429:
                self.skipped += 1
                print("⚠️  被限流，跳过 SSE 测试")
                return

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

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
                            raise AssertionError(f"Stream error: {data.get('error', 'unknown')}")
                    except json.JSONDecodeError:
                        pass

            assert len(chunks) > 0, "Should receive at least one content chunk"
            assert complete, "Stream should complete with 'complete' event"
            full_content = "".join(chunks)
            assert len(full_content) > 10, "Content should be substantial"

    async def run_all_tests(self):
        """运行所有测试"""
        print("🚀 开始 E4 端到端测试（Java 后端）\n")

        await self.setup()

        try:
            print("📋 阶段 1：认证与健康检查")
            await self.run_test("Health Check (/health)", self.test_health_check)
            await self.run_test("Health Detail (/health/detail)", self.test_health_detail)
            await self.run_test("Login (valid credentials)", self.test_login_with_valid_credentials)
            await self.run_test("Login (wrong password)", self.test_login_with_wrong_password)
            await self.run_test("Login (nonexistent user)", self.test_login_with_nonexistent_user)
            await self.run_test("Access protected endpoint without token", self.test_access_protected_endpoint_without_token)
            await self.run_test("Access protected endpoint with token", self.test_access_protected_endpoint_with_valid_token)
            await self.run_test("Get user info", self.test_get_user_info)

            print("\n📋 阶段 2：会话与对话")
            await self.run_test("Get conversations list", self.test_get_conversations)
            await self.run_test("Chat SSE stream", self.test_chat_sse_stream)

        finally:
            await self.teardown()

        # 输出汇总
        print(f"\n{'='*60}")
        print(f"📊 测试汇总：通过 {self.passed} / 失败 {self.failed} / 跳过 {self.skipped}")
        print(f"{'='*60}")

        return self.failed == 0


async def main():
    runner = E2ETestRunner()
    success = await runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
