"""
API 自动化测试脚本

测试所有已实现的 API 端点，生成测试报告
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Optional

import aiohttp


BASE_URL = "http://localhost:3000"
TEST_USER = {
    "username": f"testuser_{int(time.time())}",
    "password": "Test1234!",
    "email": f"test_{int(time.time())}@example.com",
}


class APITester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.conversation_id: Optional[int] = None
        self.results: list[dict] = []
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("=" * 80)
        print(f"API 自动化测试开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            # 1. 健康检查
            await self.test_health()
            
            # 2. 认证相关
            await self.test_register()
            await self.test_login()
            await self.test_me()
            
            # 3. 会话管理
            await self.test_create_conversation()
            await self.test_list_conversations()
            
            # 4. 聊天接口
            await self.test_chat()
            
            # 5. 行程历史
            await self.test_list_trips()
            
            # 6. 反馈接口
            await self.test_create_feedback()
            await self.test_list_feedbacks()
            
            # 7. Token 统计
            await self.test_token_usage_summary()
            
            # 8. Admin 接口
            await self.test_agent_trace()
        
        # 生成测试报告
        self.generate_report()
    
    async def test_health(self):
        """测试健康检查"""
        await self._test_endpoint(
            name="健康检查",
            method="GET",
            path="/health",
            expected_status=200,
            auth_required=False,
        )
    
    async def test_register(self):
        """测试用户注册"""
        await self._test_endpoint(
            name="用户注册",
            method="POST",
            path="/auth/register",
            data=TEST_USER,
            expected_status=201,
            auth_required=False,
        )
    
    async def test_login(self):
        """测试用户登录"""
        result = await self._test_endpoint(
            name="用户登录",
            method="POST",
            path="/auth/login",
            data={
                "username": TEST_USER["username"],
                "password": TEST_USER["password"],
            },
            expected_status=200,
            auth_required=False,
            save_result=True,
        )
        
        # 从响应中提取 token（响应格式：{code, data: {..., token}, message, error}）
        if result and isinstance(result, dict):
            if "data" in result and isinstance(result["data"], dict) and "token" in result["data"]:
                self.token = result["data"]["token"]
                print(f"    ✓ 获取到 Token")
            else:
                print(f"    ⚠ 未找到 Token in response: {result}")
    
    async def test_me(self):
        """测试获取当前用户信息"""
        await self._test_endpoint(
            name="获取当前用户信息",
            method="GET",
            path="/auth/me",
            expected_status=200,
            auth_required=True,
        )
    
    async def test_create_conversation(self):
        """测试创建会话"""
        result = await self._test_endpoint(
            name="创建会话",
            method="POST",
            path="/conversations",
            data={"title": "测试会话"},
            expected_status=201,
            auth_required=True,
            save_result=True,
        )
        
        # 从响应中提取会话 ID（响应格式：{code, data: {id, ...}, message, error}）
        if result and isinstance(result, dict) and "data" in result:
            data = result["data"]
            if isinstance(data, dict) and "id" in data:
                self.conversation_id = data["id"]
                print(f"    ✓ 创建会话 ID: {self.conversation_id}")
    
    async def test_list_conversations(self):
        """测试获取会话列表"""
        await self._test_endpoint(
            name="获取会话列表",
            method="GET",
            path="/conversations",
            expected_status=200,
            auth_required=True,
        )
    
    async def test_chat(self):
        """测试聊天接口（非流式）"""
        if not self.conversation_id:
            print("  ⚠ 跳过聊天测试（没有 conversation_id）")
            self.results.append({
                "name": "聊天接口",
                "status": "SKIPPED",
                "reason": "没有 conversation_id",
            })
            return
        
        await self._test_endpoint(
            name="聊天接口",
            method="POST",
            path="/trip/chat",
            data={
                "message": "你好，请介绍一下北京",
                "conversation_id": self.conversation_id,
            },
            expected_status=200,
            auth_required=True,
        )
    
    async def test_list_trips(self):
        """测试获取行程列表"""
        await self._test_endpoint(
            name="获取行程列表",
            method="GET",
            path="/trips",
            expected_status=200,
            auth_required=True,
        )
    
    async def test_create_feedback(self):
        """测试创建反馈"""
        # 反馈需要关联到具体的消息，需要先创建消息（通过聊天）
        # 这里跳过测试，因为需要先调用聊天接口创建消息
        print(f"  ⚠ 跳过创建反馈测试（需要先有消息）")
        self.results.append({
            "name": "创建反馈",
            "status": "SKIPPED",
            "reason": "需要先有消息",
        })
    
    async def test_list_feedbacks(self):
        """测试获取反馈列表"""
        await self._test_endpoint(
            name="获取反馈列表",
            method="GET",
            path="/feedback",
            expected_status=200,
            auth_required=True,
        )
    
    async def test_token_usage_summary(self):
        """测试 Token 使用统计"""
        await self._test_endpoint(
            name="Token 使用统计",
            method="GET",
            path="/stats/token-usage/summary",
            expected_status=200,
            auth_required=True,
        )
    
    async def test_agent_trace(self):
        """测试 Agent 执行轨迹"""
        # 需要管理员权限，跳过测试
        print(f"  ⚠ 跳过 Agent 执行轨迹测试（需要管理员权限）")
        self.results.append({
            "name": "Agent 执行轨迹",
            "status": "SKIPPED",
            "reason": "需要管理员权限",
        })
    
    async def _test_endpoint(
        self,
        name: str,
        method: str,
        path: str,
        data: Optional[dict] = None,
        expected_status: int = 200,
        auth_required: bool = False,
        save_result: bool = False,
    ) -> Optional[dict]:
        """测试单个端点"""
        print(f"  🔍 测试: {name} ({method} {path})")
        
        headers = {}
        if auth_required and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            url = f"{self.base_url}{path}"
            
            if method.upper() == "GET":
                async with self.session.get(url, headers=headers) as resp:
                    status = resp.status
                    try:
                        body = await resp.json()
                    except:
                        body = await resp.text()
            elif method.upper() == "POST":
                async with self.session.post(url, json=data, headers=headers) as resp:
                    status = resp.status
                    try:
                        body = await resp.json()
                    except:
                        body = await resp.text()
            else:
                print(f"    ✗ 不支持的方法: {method}")
                return None
            
            # 检查状态码
            if status == expected_status:
                print(f"    ✓ 状态码正确: {status}")
                self.results.append({
                    "name": name,
                    "method": method,
                    "path": path,
                    "status": "PASSED",
                    "status_code": status,
                })
                
                if save_result and isinstance(body, dict):
                    return body
                return None
            else:
                print(f"    ✗ 状态码错误: 期望 {expected_status}, 实际 {status}")
                print(f"    响应: {body}")
                self.results.append({
                    "name": name,
                    "method": method,
                    "path": path,
                    "status": "FAILED",
                    "expected_status": expected_status,
                    "actual_status": status,
                    "response": body,
                })
                return None
        
        except Exception as e:
            print(f"    ✗ 请求失败: {e}")
            self.results.append({
                "name": name,
                "method": method,
                "path": path,
                "status": "ERROR",
                "error": str(e),
            })
            return None
    
    def generate_report(self):
        """生成测试报告"""
        print()
        print("=" * 80)
        print("测试报告")
        print("=" * 80)
        print()
        
        # 统计
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASSED")
        failed = sum(1 for r in self.results if r["status"] == "FAILED")
        errors = sum(1 for r in self.results if r["status"] == "ERROR")
        skipped = sum(1 for r in self.results if r["status"] == "SKIPPED")
        
        print(f"总测试数: {total}")
        print(f"  ✓ 通过: {passed}")
        print(f"  ✗ 失败: {failed}")
        print(f"  ⚠ 错误: {errors}")
        print(f"  - 跳过: {skipped}")
        print()
        
        # 详细结果
        if failed > 0 or errors > 0:
            print("失败/错误详情:")
            print("-" * 80)
            for r in self.results:
                if r["status"] in ["FAILED", "ERROR"]:
                    print(f"  {r['name']} ({r['method']} {r['path']})")
                    if r["status"] == "FAILED":
                        print(f"    期望状态码: {r.get('expected_status')}")
                        print(f"    实际状态码: {r.get('actual_status')}")
                        print(f"    响应: {r.get('response')}")
                    else:
                        print(f"    错误: {r.get('error')}")
                    print()
        
        print("=" * 80)
        
        # 保存到文件
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped,
            },
            "results": self.results,
        }
        
        report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"测试报告已保存: {report_file}")


async def main():
    """主函数"""
    # 检查服务器是否运行
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/health") as resp:
                if resp.status != 200:
                    print(f"⚠ 服务器未运行或健康检查失败 (状态码: {resp.status})")
                    print(f"请确保服务器正在运行: cd trip-backend && python src/main.py")
                    return
    except Exception as e:
        print(f"⚠ 无法连接到服务器: {e}")
        print(f"请确保服务器正在运行: cd trip-backend && python src/main.py")
        return
    
    # 运行测试
    tester = APITester(BASE_URL)
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
