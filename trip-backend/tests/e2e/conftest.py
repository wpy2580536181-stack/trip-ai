"""E2E 测试 fixture — 启动后端子进程 + 等待就绪

- backend_server: session-scoped，仅启动一次后端
- auth_token: session-scoped，仅登录一次
- client / auth_client: function-scoped，每个测试独立 httpx 客户端
"""

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
PYTHON = str(PROJECT_DIR / ".venv" / "bin" / "python")
E2E_PORT = int(os.getenv("E2E_PORT", "3001"))
BASE_URL = f"http://localhost:{E2E_PORT}"

# 环境变量（放松限流）
_E2E_ENV = {
    **os.environ,
    "RATE_LIMIT_AUTH_MAX": "99999",
    "RATE_LIMIT_AUTH_WINDOW": "1",
    "RATE_LIMIT_GLOBAL_MAX": "999999",
    "RATE_LIMIT_CHAT_MAX": "99999",
    "RATE_LIMIT_RECOMMEND_MAX": "99999",
}


@pytest_asyncio.fixture(scope="session")
async def backend_server():
    """启动后端服务（session 级别，仅启动一次）"""
    proc = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "src.main:app",
         "--host", "0.0.0.0", "--port", str(E2E_PORT),
         "--log-level", "error"],
        cwd=PROJECT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=_E2E_ENV,
    )

    # 等待后端就绪（最多 30 秒）
    for i in range(15):
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=5) as c:
                r = await c.post("/api/user/login",
                                 json={"username": "eval-test", "password": "EvalTest@2026"})
                if r.status_code == 200:
                    print(f"Backend ready (attempt {i + 1}, port {E2E_PORT})")
                    break
        except Exception:
            pass
        time.sleep(2)
    else:
        proc.kill()
        raise RuntimeError(f"Backend failed to start on port {E2E_PORT}")

    yield proc

    # 清理
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("Backend stopped")


@pytest_asyncio.fixture(scope="session")
async def auth_token(backend_server):
    """预先获取的 JWT token（session 级，只登录一次）"""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        resp = await c.post("/api/user/login",
                            json={"username": "eval-test", "password": "EvalTest@2026"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        token = data.get("data", {}).get("token")
        assert token, f"No token in response: {data}"
        return token


@pytest_asyncio.fixture
async def client():
    """每个测试函数获得一个独立的 httpx 客户端"""
    async with httpx.AsyncClient(base_url=BASE_URL) as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(client, auth_token):
    """每个测试函数获得一个已登录的客户端"""
    client.headers["Authorization"] = f"Bearer {auth_token}"
    return client
