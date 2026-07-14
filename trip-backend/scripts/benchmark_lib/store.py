"""基准测试结果存储与环境快照"""

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "performance-data"


def get_env() -> dict:
    """环境快照（与 Node 版结构一致）"""
    info = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "arch": platform.machine(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        info["cpus"] = psutil.cpu_count(logical=True)
        info["totalMemMB"] = round(mem.total / 1024 / 1024)
        info["freeMemMB"] = round(mem.available / 1024 / 1024)
    return info


def percentile(values: list[float], p: float) -> float:
    """计算百分位数（与 Node 版一致）"""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int((len(sorted_vals) - 1) * (p / 100.0))
    return sorted_vals[idx]


def save_result(name: str, data: dict) -> str:
    """保存基准测试结果到 JSON 文件"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath = DATA_DIR / f"{name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Result saved: {filepath}")
    return str(filepath)
