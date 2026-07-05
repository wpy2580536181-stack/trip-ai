"""MCP 冒烟测试脚本。

对标 Node.js scripts/mcp-smoke.ts，验证高德 MCP 集成是否正常工作。
独立可运行：python -m eval.mcp_smoke

MCP 不可用时优雅跳过而非崩溃。
"""

import asyncio
import os
import sys
import shutil

# ── 彩色输出 ──────────────────────────────────────────────

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _pass(msg: str) -> None:
    print(f"  {_GREEN}✔ PASS{_RESET}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {_RED}✘ FAIL{_RESET}  {msg}")


def _skip(msg: str) -> None:
    print(f"  {_YELLOW}⊘ SKIP{_RESET}  {msg}")


def _info(msg: str) -> None:
    print(f"  {_CYAN}ℹ{_RESET}  {msg}")


def _header(msg: str) -> None:
    print(f"\n{_BOLD}[MCP Smoke]{_RESET} {msg}")


# ── 前置检查 ──────────────────────────────────────────────

def _check_prerequisites() -> str | None:
    """检查 MCP 运行前置条件，返回跳过原因或 None（表示可以继续）。"""
    # 检查 node 是否可用
    if shutil.which("node") is None:
        return "node 未安装，MCP server 需要 Node.js 运行时"

    # 检查 AMAP_MCP_SERVER_PATH 环境变量或 .env 中是否配置
    mcp_path = os.environ.get("AMAP_MCP_SERVER_PATH", "")
    if not mcp_path:
        # 尝试从 .env 文件读取
        env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.isfile(env_file):
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("AMAP_MCP_SERVER_PATH="):
                        mcp_path = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not mcp_path:
        return "未配置 AMAP_MCP_SERVER_PATH，无法启动 MCP server"
    if not os.path.isfile(mcp_path):
        return f"AMAP_MCP_SERVER_PATH 指向的文件不存在: {mcp_path}"

    return None


# ── 核心测试流程 ──────────────────────────────────────────

async def _run_smoke() -> tuple[int, int, int]:
    """运行冒烟测试，返回 (passed, failed, skipped) 计数。"""
    passed = 0
    failed = 0
    skipped = 0

    # ── 前置检查 ──
    skip_reason = _check_prerequisites()
    if skip_reason:
        _skip(f"前置条件不满足: {skip_reason}")
        return 0, 0, 1

    # ── Step 1: 启动 MCP 进程 ──
    _header("Step 1: 启动 Amap MCP 进程")
    try:
        from src.services.mcp.amap_process import start_amap_mcp_server, stop_amap_mcp_server
        from src.services.mcp.amap_client import list_tools, call_tool, close_mcp_process

        process = await asyncio.wait_for(start_amap_mcp_server(), timeout=15.0)
        if process.returncode is not None:
            _fail("MCP 进程启动后立即退出")
            failed += 1
            return passed, failed, skipped
        _pass("MCP server 进程已启动")
        passed += 1
    except Exception as e:
        _fail(f"启动 MCP 进程失败: {e}")
        _skip("后续步骤因 MCP 进程不可用而跳过")
        skipped += 1
        return passed, failed, skipped + 1

    # ── Step 2: 列举可用工具 ──
    _header("Step 2: 列举可用工具")
    tools: list[dict] = []
    try:
        tools = await asyncio.wait_for(list_tools(), timeout=15.0)
        if not tools:
            _fail("未获取到任何 MCP 工具")
            failed += 1
        else:
            _pass(f"获取到 {len(tools)} 个工具:")
            for t in tools:
                _info(f"  - {t.get('name', '?')}: {t.get('description', '(无描述)')}")
            passed += 1
    except Exception as e:
        _fail(f"列举工具失败: {e}")
        failed += 1

    # ── Step 3: 调用天气工具（如果可用） ──
    _header("Step 3: 调用天气工具")
    weather_tool = next(
        (t for t in tools if "weather" in t.get("name", "").lower()),
        None,
    )
    if weather_tool is None:
        _skip("未找到天气相关工具，跳过调用测试")
        skipped += 1
    else:
        tool_name = weather_tool["name"]
        try:
            _info(f"调用 {tool_name}(city='北京')...")
            result = await asyncio.wait_for(
                call_tool(tool_name, {"city": "北京"}),
                timeout=30.0,
            )
            # 验证响应格式
            if not result or not isinstance(result, str):
                _fail(f"天气工具返回格式异常: type={type(result).__name__}, value={result!r}")
                failed += 1
            elif len(result.strip()) == 0:
                _fail("天气工具返回空字符串")
                failed += 1
            else:
                preview = result[:500]
                _pass(f"天气工具调用成功，响应 ({len(result)} 字符):")
                _info(f"  {preview}")
                passed += 1
        except asyncio.TimeoutError:
            _fail(f"调用 {tool_name} 超时（30s）")
            failed += 1
        except Exception as e:
            _fail(f"调用 {tool_name} 失败: {e}")
            failed += 1

    # ── Step 4: 验证工具列表结构 ──
    _header("Step 4: 验证工具列表结构")
    if tools:
        struct_ok = True
        for t in tools:
            if "name" not in t:
                _fail(f"工具缺少 name 字段: {t}")
                struct_ok = False
                break
        if struct_ok:
            _pass("所有工具均包含 name 字段")
            passed += 1
        else:
            failed += 1
    else:
        _skip("无工具数据，跳过结构验证")
        skipped += 1

    # ── 清理 ──
    _header("清理")
    try:
        await close_mcp_process()
        _info("MCP server 进程已关闭")
    except Exception as e:
        _info(f"关闭 MCP 进程时出现异常（可忽略）: {e}")

    return passed, failed, skipped


# ── 入口 ─────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{_BOLD}{'═' * 50}{_RESET}")
    print(f"{_BOLD}  MCP 冒烟测试{_RESET}")
    print(f"{_BOLD}{'═' * 50}{_RESET}")

    passed, failed, skipped = await _run_smoke()

    total = passed + failed + skipped
    print(f"\n{_BOLD}{'─' * 50}{_RESET}")
    print(
        f"  结果: 共 {total} 项  "
        f"{_GREEN}{passed} 通过{_RESET}  "
        f"{_RED}{failed} 失败{_RESET}  "
        f"{_YELLOW}{skipped} 跳过{_RESET}"
    )
    print(f"{_BOLD}{'─' * 50}{_RESET}\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
