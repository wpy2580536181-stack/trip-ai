#!/usr/bin/env python3
"""
验证 Amap MCP 配置：启动 MCP server → 调用 maps_text_search → 验证返回结构

用法：
  cd trip-backend && .venv/bin/python test_amap_mcp_config.py
"""

import asyncio
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from src.config.settings import settings
from src.services.mcp.amap_client import _ensure_mcp_process, call_tool, close_mcp_process
from src.services.mcp.guards import reset_metrics


async def main():
    print("🔧 检查配置...")
    print(f"   AMAP_MAPS_API_KEY 已配置: {bool(settings.amap_maps_api_key)}")
    print(f"   AMAP_MCP_SERVER_PATH: {repr(settings.amap_mcp_server_path)}")

    if not settings.amap_maps_api_key:
        print("\n❌ AMAP_MAPS_API_KEY 未配置，退出")
        return

    # 重置指标
    reset_metrics()

    # 启动 MCP server
    print("\n🚀 启动 Amap MCP server...")
    try:
        proc = await _ensure_mcp_process()
        print(f"   ✅ 进程已启动 (PID {proc.pid})")
    except Exception as e:
        print(f"   ❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 等待 server 就绪
    print("   ⏳ 等待 server 就绪 (2s)...")
    await asyncio.sleep(2)

    # 测试 maps_text_search
    print("\n📡 测试 maps_text_search('故宫博物院', '北京')...")
    try:
        result = await call_tool(
            "maps_text_search",
            {"keywords": "故宫博物院", "city": "北京"},
        )
        print(f"   ✅ 调用成功")
        print(f"   返回类型: {type(result).__name__}")
        print(f"   返回内容 (前800字符):\n   {str(result)[:800]}")

        # 简单解析验证
        import json
        data = json.loads(result)
        pois = data.get("pois", [])
        if pois:
            poi = pois[0]
            name = poi.get("name", "?")
            addr = poi.get("address", "?")
            photos = poi.get("photos", {})
            has_photo = bool(photos.get("url") if isinstance(photos, dict) else False)
            print(f"\n   📍 POI 信息:")
            print(f"   - 名称: {name}")
            print(f"   - 地址: {addr}")
            print(f"   - 有图片: {'✅' if has_photo else '❌'}")
        else:
            print("\n   ⚠️ 返回无 POI 数据")

    except Exception as e:
        print(f"   ❌ 调用失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        try:
            await close_mcp_process()
            print("\n🧹 MCP server 已关闭")
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
