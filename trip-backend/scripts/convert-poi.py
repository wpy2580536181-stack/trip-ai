#!/usr/bin/env python3
"""
POI 转换脚本 - 用 LLM 批量生成 Spot 数据
读取 data/poi_raw/*.json，调用 DeepSeek API 生成 description/tags/rating，
输出为 data/spots/{城市}.json。
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Load .env (hardcoded path as fallback)
def load_env():
    # Try multiple possible paths
    candidates = [
        Path(__file__).parent.parent / '.env',  # trip-server/.env (most reliable)
        Path(__file__).parent / '.env',
        Path.cwd() / '.env',
    ]
    for env_path in candidates:
        if env_path.exists():
            content = env_path.read_text('utf-8')
            for line in content.split('\n'):
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or '=' not in stripped:
                    continue
                key, val = stripped.split('=', 1)
                key, val = key.strip(), val.strip()
                if key not in os.environ:
                    os.environ[key] = val
            print(f"[DEBUG] Loaded .env from {env_path} ✓", file=sys.stderr, flush=True)
            return
    print(f"[DEBUG] No .env found! Checked: {candidates}", file=sys.stderr, flush=True)

load_env()

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-v4-flash')

PROJECT_ROOT = str(Path(__file__).parent.parent)  # trip-server (scripts 的父目录)
POI_RAW_DIR = Path(PROJECT_ROOT) / 'data' / 'poi_raw'
SPOTS_DIR = Path(PROJECT_ROOT) / 'data' / 'spots'
SPOTS_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_MAP = {'scenic': 'attraction', 'food': 'food', 'hotel': 'hotel'}


def extract_json(text: str) -> dict | None:
    """从 LLM 输出中提取合法的 JSON 对象"""
    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 尝试提取第一个合法的 { ... }
    # 找到最外层的 { } 配对
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start:i+1]
                # 尝试修复常见的 JSON 问题：
                # 去掉末尾多余的逗号和括号
                chunk = re.sub(r',\s*}', '}', chunk)
                chunk = re.sub(r',\s*\]', ']', chunk)
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    pass

    # 3. 最后尝试用正则提取关键字段
    return None


def llm_generate(poi: dict, category: str) -> dict:
    """调用 DeepSeek LLM 生成 Spot 数据"""
    system_prompt = """你是一个旅游数据标注助手。根据 POI 信息生成结构化 JSON。

输出必须是合法的 JSON，遵守以下规则：
1. description 字段中的所有双引号必须用反斜杠转义
2. 不要输出任何解释文字
3. 不要输出 markdown 代码块标记
4. 直接输出从 { 开始到 } 结束的 JSON 对象

格式示例：
{"name":"武侯祠","city":"成都","category":"attraction","description":"武侯祠是...","tags":["三国","博物馆"],"avgCost":50,"duration":"2小时","openTime":"08:00-18:00","rating":4.6}"""

    user_prompt = f"名称：{poi['name']}\n类别：{category}\n类型：{poi.get('type','')}\n地址：{poi.get('address','')}\n区域：{poi.get('adname','')}"

    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    body = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 500,
    }).encode('utf-8')

    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
    })

    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode('utf-8'))
    content = data['choices'][0]['message']['content'].strip()

    spot = extract_json(content)
    if spot is None:
        raise json.JSONDecodeError("Could not extract valid JSON", content, 0)

    spot['city'] = poi.get('adname', poi.get('cityname', ''))
    return spot


def fallback_spot(poi: dict, category: str, city: str) -> dict:
    """降级：不依赖 LLM 的默认 Spot 数据"""
    cat_label = {'attraction': '旅游景点', 'food': '美食餐厅', 'hotel': '住宿地点'}.get(category, '地点')
    return {
        'name': poi['name'],
        'city': city,
        'category': category,
        'description': f"{poi['name']} 是{city}的{cat_label}，位于{poi.get('adname', '')}。地址：{poi.get('address', '')}。",
        'tags': [city],
        'avgCost': 0,
        'duration': '',
        'openTime': '全天',
        'rating': 3.5,
    }


def main():
    print("=== POI 转换脚本 ===", flush=True)
    print(f"DEEPSEEK_API_KEY present: {bool(os.environ.get('DEEPSEEK_API_KEY'))}", flush=True)
    print(f"PROJECT_ROOT: {PROJECT_ROOT}", flush=True)
    print(f"POI_RAW_DIR exists: {POI_RAW_DIR.exists()}", flush=True)
    print(f"Files: {list(POI_RAW_DIR.glob('*.json'))}", flush=True)

    city_files = sorted([f for f in POI_RAW_DIR.glob('*.json') if not f.name.startswith('.')])
    print(f"找到 {len(city_files)} 个城市原始数据\n")

    all_spots_by_city = {}
    total_success = 0
    total_failed = 0

    for city_file in city_files:
        city_name = city_file.stem
        print(f">>> 处理 {city_name} ...")

        raw = json.loads(city_file.read_text('utf-8'))
        spots = []

        for category_key in ['scenic', 'food', 'hotel']:
            mapped_cat = CATEGORY_MAP[category_key]
            pois = raw.get(category_key, [])

            for poi in pois:
                spot = None
                for attempt in range(3):
                    try:
                        spot = llm_generate(poi, mapped_cat)
                        spot['city'] = city_name
                        spots.append(spot)
                        print(f"  ✓ {poi['name']} → {mapped_cat} ({spot['rating']})", flush=True)
                        total_success += 1
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(2)
                            continue
                        print(f"  ✗ {poi['name']} 失败: {e}", flush=True)
                        spot = fallback_spot(poi, mapped_cat, city_name)
                        spots.append(spot)
                        total_failed += 1

                time.sleep(0.8)  # LLM 限频

        all_spots_by_city[city_name] = spots

        # 每城市写入一次
        out_path = SPOTS_DIR / f'{city_name}.json'
        out_path.write_text(json.dumps(spots, ensure_ascii=False, indent=2), 'utf-8')
        print(f"  → {out_path.name}: {len(spots)} 个 Spot\n")

    total = sum(len(v) for v in all_spots_by_city.values())
    print(f"=== 完成 === 共转换 {total} 个 Spot (成功:{total_success}, 降级:{total_failed})")
    print(f"\n下一步：")
    print(f"1. 检查 {SPOTS_DIR} 目录下的转换结果")
    print(f"2. 修改 seed-knowledge.ts 支持自动发现城市")
    print(f"3. 运行: cd trip-server && npx ts-node prisma/seed-knowledge.ts")


if __name__ == '__main__':
    main()
