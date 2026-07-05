"""获取基准测试认证 token（对应 Node 版 lib/auth.ts）"""

import os
import time

import httpx

# 默认测试凭据（与 Node 版一致）
EVAL_USERNAME = os.getenv("EVAL_USERNAME", "eval-test")
EVAL_PASSWORD = os.getenv("EVAL_PASSWORD", "EvalTest@2026")
BASE_URL = os.getenv("BASE_URL", "http://localhost:3000")

# 内存缓存 token，避免压测间频繁重新登录触发 rate limit
_token_cache: dict[str, str] = {}  # base_url -> token
_token_max_retries = int(os.getenv("AUTH_MAX_RETRIES", "12"))
_token_retry_delay = float(os.getenv("AUTH_RETRY_DELAY", "5"))


def get_eval_credentials() -> dict:
    return {"username": EVAL_USERNAME, "password": EVAL_PASSWORD}


def get_auth_token(base_url: str = BASE_URL, force_refresh: bool = False) -> str:
    """通过登录接口获取 JWT token，带内存缓存和限流重试

    Args:
        base_url: API 基础 URL
        force_refresh: 强制重新登录（忽略缓存）
    """
    # 缓存命中
    cached = _token_cache.get(base_url)
    if cached and not force_refresh:
        return cached

    url = f"{base_url.rstrip('/')}/api/user/login"

    for attempt in range(_token_max_retries):
        try:
            resp = httpx.post(url, json=get_eval_credentials(), timeout=10)

            if resp.status_code == 429:
                remaining = _token_retry_delay * (attempt + 1)
                print(f"  [auth] rate limited (attempt {attempt + 1}), "
                      f"retrying in {remaining:.0f}s...")
                time.sleep(remaining)
                continue

            resp.raise_for_status()
            data = resp.json()
            token = data.get("data", {}).get("token")
            if not token:
                raise RuntimeError(f"Failed to extract token from response: {data}")

            _token_cache[base_url] = token
            return token

        except httpx.TimeoutException:
            if attempt == _token_max_retries - 1:
                raise
            print(f"  [auth] timeout (attempt {attempt + 1}), retrying...")
            time.sleep(_token_retry_delay)

    raise RuntimeError(f"Failed to get auth token after {_token_max_retries} retries")


def get_auth_header(base_url: str = BASE_URL, force_refresh: bool = False) -> dict:
    """获取包含 Authorization 头的字典"""
    token = get_auth_token(base_url, force_refresh=force_refresh)
    return {"Authorization": f"Bearer {token}"}


def clear_token_cache():
    """清理 token 缓存（测试用）"""
    _token_cache.clear()
