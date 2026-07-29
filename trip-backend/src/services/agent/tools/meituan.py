"""美团酒旅 CLI 工具：沙箱化封装 `ht-ai query`，供 meituan-travel skill 在 Python 后端执行。

安全要点：
- 仅允许运行受限的 `ht-ai query` 子命令；通过 subprocess 列表式传参（无 shell），
  从根本上杜绝命令注入。
- 仅当环境变量 MEITUAN_HT_TOKEN 配置后才发起请求；缺失时明确报错而非带空 token 调用。
- 超时（150s）保护，避免美团接口长耗时拖垮对话链路。

依赖：运行环境需安装 npx（Node.js）且已配置 MEITUAN_HT_TOKEN。
"""

import asyncio
import logging
import os
import re

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_CMD = "npx"
_PKG = "@meituan-travel/ht-ai@latest"
_CHANNEL = "meituan-developer"
_TIMEOUT = 150  # 美团接口官方提示约 1-2 分钟


def _sanitize(value: str) -> str:
    """清理控制字符，仅保留可见内容（换行/制表/NUL 等可能导致 CLI 参数异常）。

    由于采用列表式传参（无 shell），无需转义引号/分号等，这里只剥离控制字符。
    """
    if not value:
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", " ", value).strip()


@tool
async def meituan_query_tool(query: str, origin_query: str = "", city: str = "") -> str:
    """调用美团酒旅官方 CLI 查询机票/酒店/火车票/景点门票（等价于执行
    `npx @meituan-travel/ht-ai@latest query`）。

    仅在用户明确需要美团官方酒旅数据（如「订酒店」「买机票」「门票」）时使用。
    query 为用户自然语言查询；city 为目标城市（缺省时由接口默认）。

    Args:
        query: 用户的自然语言查询（必填）
        origin_query: 用户原始完整输入（用于统计，缺省同 query）
        city: 城市名称（可选）
    """
    if not query or not query.strip():
        return "错误：查询内容为空。"

    token = os.getenv("MEITUAN_HT_TOKEN")
    if not token:
        return (
            "未配置 MEITUAN_HT_TOKEN，无法调用美团酒旅接口。"
            "请在运行环境配置该环境变量后重试。"
        )

    safe_query = _sanitize(query)
    safe_origin = _sanitize(origin_query) or safe_query
    safe_city = _sanitize(city) if city else ""

    cmd = [
        _CMD, _PKG, "query",
        "--query", safe_query,
        "--origin-query", safe_origin,
        "--channel", _CHANNEL,
    ]
    if safe_city:
        cmd += ["--city", safe_city]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except FileNotFoundError:
        return "未找到 npx，无法执行美团酒旅 CLI。请确认运行环境已安装 Node.js 与 npx。"
    except asyncio.TimeoutError:
        return "美团酒旅接口请求超时（>150s），请稍后重试或更换问法。"
    except Exception as e:  # noqa: BLE001
        logger.warning("meituan_query|failed: %s", e)
        return f"美团酒旅查询失败：{e}"

    out = (stdout or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode == 3:
        return "美团鉴权失败（exit 3），请检查 MEITUAN_HT_TOKEN 是否正确配置。"
    if not out:
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        return f"美团查询未返回内容：{err[:500]}" if err else "美团未返回内容。"
    return out
