"""按景点名称抓取中文/英文维基百科词条（文本层 ETL - 数据源 A）.

入：data/spots/{city}.json（事实层快照，含 name/city）
出：data/wiki_raw/{city}.json（每个 spot 一条维基抽取：title/extract/source_url/pageid）

抓取策略（准确率优先，避免错挂）：
  1) 精确标题查询（titles=，带 redirects）优先；
  2) 精确未命中 → 退化为 MediaWiki list=search 模糊检索（S1：srsearch 追加城市名提升召回），
     但**仅接受标题与查询词有重叠的候选**（容忍「拉萨布达拉宫」vs 词条「布达拉宫」这类变体）；
     若没有任何候选标题与查询词重叠，视为维基无对应词条，直接跳过；
  3) 仍未命中 → Wikidata 实体检索兜底（S1：景点名↔维基条目别名/跨语言匹配，不依赖坐标），
     取标签相关的实体对应的中文维基条目标题再抽正文；
  4) 相关性以「景点名」为核心判定：核心名须出现在条目标题或正文，否则拒绝兜底垃圾
     （避免把无关人物页错挂到餐饮/品牌类 POI）；仅「公园/广场/酒店」等泛化公共地名
     允许用「城市出现在正文」来跨城同名消歧。

合规：维基百科内容采用 CC BY-SA 授权，仅用于个人作品集检索增强，非商业。
限频：默认每任务 0.02s 间隔 + 并发信号量；代理偶发 TLS 抖动时指数退避重试。
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import List, Dict, Any, Optional

# 项目根目录（脚本位于 trip-backend/scripts/）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPOTS_DIR = os.path.join(ROOT, "data", "spots")
WIKI_RAW_DIR = os.path.join(ROOT, "data", "wiki_raw")

WIKI_ENDPOINTS = {
    "zh": "https://zh.wikipedia.org/w/api.php",
    "en": "https://en.wikipedia.org/w/api.php",
}
# Wikidata 实体检索（用于「景点名 ↔ 维基条目」的别名/跨语言兜底，不依赖坐标）
WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php"
UA = "TripRAGBot/0.1 (educational RAG demo; contact: user@example.com)"
HEADERS = {
    "User-Agent": UA,
    "Connection": "close",  # 避免复用被代理抖动掐断的 keep-alive 连接
}

# 高度泛化的 POI 后缀 / 通用词条：要求「城市专属」文章才能采信，避免把通用概念页
# （如「牛肉面」「教堂」「山」「湖」）错挂到具体城市 POI。覆盖：地名/建筑/宗教/餐饮/地理等。
GENERIC_SUFFIXES = (
    # 原有（地名/建筑/教育/文博）
    "公园", "广场", "酒店", "宾馆", "旅馆", "大院", "小区",
    "大厦", "大楼", "路", "街", "店", "中学", "小学", "医院",
    "博物馆", "纪念馆", "展馆", "艺术馆", "美术馆",
    "饭店", "餐厅", "火锅", "小吃", "美食", "大学", "学院",
    # 餐饮 / 食物（避免「牛肉面」概念页错挂「大西北牛肉面」）
    "面", "饭", "粉", "汤", "粥", "包", "饺", "饼", "糕", "糖",
    "茶", "酒", "咖啡", "菜", "肉", "鱼", "鸡", "烧烤", "快餐", "餐馆",
    # 宗教 / 建筑（避免「教堂」概念页错挂「天主堂」）
    "堂", "寺", "庙", "观", "宫", "殿", "塔", "桥", "楼", "馆", "院",
    "亭", "阁", "陵", "祠", "碑", "门", "墙", "城", "池", "井", "泉", "洞",
    # 自然地理（避免「山/湖/江」概念页错挂具体山水）
    "山", "河", "湖", "江", "海", "岛", "峰", "岭", "谷", "峡",
    "草原", "沙漠", "林", "苑", "园", "村", "镇", "乡",
    # 商业 / 交通 / 设施
    "市场", "商场", "超市", "书店", "银行", "公司", "工厂", "基地",
    "中心", "站", "场", "港", "码头", "街道",
)


def _core_name(name: str) -> str:
    """去掉括号里的分店/地址后缀：'X(YYY店)' -> 'X'."""
    return re.sub(r"[（(].*?[）)]", "", name or "").strip()


def _query_term(spot_name: str, city: str) -> str:
    """用于检索的词：去分店后缀 + 去掉城市前缀（'拉萨布达拉宫' -> '布达拉宫'）."""
    n = _core_name(spot_name)
    if city and n.startswith(city):
        n = n[len(city):].strip()
    return n or spot_name


def _api_query(lang: str, title: str, retries: int = 4) -> Optional[Dict[str, Any]]:
    """精确标题查询 extracts（纯文本）。带指数退避重试（代理偶发 TLS 抖动）."""
    base = WIKI_ENDPOINTS.get(lang, WIKI_ENDPOINTS["zh"])
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "exsectionformat": "wiki",  # 让纯文本 extract 保留 == 标题 ==，供 ingest 按段切分
        # 注意：绝不能传 exintro=0。实测 MediaWiki 在 exsectionformat=wiki 下，
        # 显式 exintro=0 反而会让 extract 退化为无 == 的纯引言（仅 ~intro 长度），
        # 导致 chunk_text 的 == 分段分支永远拿不到段落标记。省略 exintro 才返回完整带 == 正文。
        "redirects": "1",
        "titles": title,
        "format": "json",
    }
    url = base + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return None
            page = next(iter(pages.values()))
            if "missing" in page:
                return None
            extract = page.get("extract", "")
            if not extract or len(extract) < 20:
                return None
            return {
                "pageid": page.get("pageid"),
                "title": page.get("title", title),
                "extract": extract,
                "source_url": f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(page.get('title', title))}",
            }
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < retries:
                # 维基限流：尊重 Retry-After（秒），最长退避 30s
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    ra = min(float(ra), 30.0) if ra else 8.0
                except (TypeError, ValueError):
                    ra = 8.0
                time.sleep(ra + 0.5)
            elif attempt < retries:
                time.sleep(min(8.0, 1.0 * (2 ** attempt)) + 0.2)
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(min(8.0, 1.0 * (2 ** attempt)) + 0.2)
    if retries >= 0:
        print(f"  [warn] 查询失败 {title!r}: {last_err}")
    return None


def _search_query(lang: str, query: str, name: Optional[str] = None,
                  city: Optional[str] = None, retries: int = 3,
                  max_candidates: int = 3) -> Optional[Dict[str, Any]]:
    """模糊检索：list=search 取与查询词有标题重叠的候选，逐个取 extracts 并用
    _is_relevant 把关，返回第一个通过相关性判定的结果。

    关键修正：
      - 若没有任何候选标题与查询词重叠（维基无对应词条），直接返回 None，
        绝不拿 list=search 的 top1 兜底——那往往是完全无关的人物/消歧页；
      - **遍历候选**（而非只取第一个）：搜索排序可能把泛化消歧页（「人民公园」）
        排在城市专属条目（「上海人民公园」）之前，只取第一个会取到泛化页被拒后
        直接返回 None；遍历可按「城市专属优先」排序后逐个试，命中真正的条目；
      - S1 改进：srsearch 追加城市名（「人民公园」→「人民公园 上海」）提升召回；
        标题重叠判定仍用原始 query（景点名），不被城市词干扰。
    """
    base = WIKI_ENDPOINTS.get(lang, WIKI_ENDPOINTS["zh"])
    srsearch = f"{query} {city}".strip() if city else query
    params = {
        "action": "query",
        "list": "search",
        "srsearch": srsearch,
        "srlimit": 5,
        "format": "json",
    }
    url = base + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("query", {}).get("search", [])
            if not hits:
                return None
            # 仅保留标题与查询词(景点名)有重叠的候选（容忍「拉萨布达拉宫」vs「布达拉宫」等变体）
            candidates = [
                h["title"]
                for h in hits
                if query in (h.get("title") or "") or (h.get("title") or "") in query
            ]
            if not candidates:
                return None
            # 城市专属条目优先（标题含城市 / 泛化地名下城市作用域命中），其余在后
            if city:
                candidates.sort(
                    key=lambda t: 0 if (city in t or _city_scoped(city, t, "", query))
                    else 1
                )
            # 逐个取 extract 并用 _is_relevant 把关，返回第一个通过者（最多前 N 个候选，降 miss 成本）
            for title in candidates[:max_candidates]:
                r = _api_query(lang, title, retries=1)
                if r and (name is None or _is_relevant(name, city, r["title"], r["extract"])):
                    return r
            return None
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < retries:
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    ra = min(float(ra), 30.0) if ra else 8.0
                except (TypeError, ValueError):
                    ra = 8.0
                time.sleep(ra + 0.5)
            elif attempt < retries:
                time.sleep(min(6.0, 1.0 * (2 ** attempt)) + 0.2)
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(min(6.0, 1.0 * (2 ** attempt)) + 0.2)
    print(f"  [warn] 搜索失败 {query!r}: {last_err}")
    return None


def _wikidata_sitelink(qid: str, lang: str, retries: int = 2) -> Optional[str]:
    """取 Wikidata 实体 Qid 对应的中文维基条目标题（sitelink）."""
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "sitefilter": f"{lang}wiki",
        "format": "json",
    }
    url = WIKIDATA_ENDPOINT + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            e = data.get("entities", {}).get(qid, {})
            sl = e.get("sitelinks", {}).get(f"{lang}wiki", {})
            return sl.get("title")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    ra = min(float(ra), 30.0) if ra else 8.0
                except (TypeError, ValueError):
                    ra = 8.0
                time.sleep(ra + 0.5)
            elif attempt < retries:
                time.sleep(min(4.0, 1.0 * (2 ** attempt)) + 0.2)
        except Exception:
            if attempt < retries:
                time.sleep(min(4.0, 1.0 * (2 ** attempt)) + 0.2)
    return None


def _wikidata_search(lang: str, term: str, city: Optional[str] = None, retries: int = 3) -> Optional[str]:
    """Wikidata 实体检索兜底（S1 新增）：用景点名(可加城市)搜 Wikidata 实体，
    取一个标签/描述与景点名相关的实体，返回其 zh 维基条目标题。

    解决「景点名 ≠ 维基标题」但 Wikidata 有别名/跨语言对应」的漏配
    （例：搜『外滩』→ Wikidata『The Bund』zh 标签『外滩』→ 中文维基『外滩』）。
    相关性由调用方 _is_relevant 最终把关，本函数只保证返回真实存在的条目标题。
    """
    params = {
        "action": "wbsearchentities",
        "search": term,
        "language": lang,
        "format": "json",
        "limit": 5,
    }
    url = WIKIDATA_ENDPOINT + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for e in data.get("search", []):
                label = e.get("label") or ""
                desc = e.get("description") or ""
                # 标签与景点名有重叠，或描述里点名城市（给泛化地名一个机会）
                if term in label or label in term or (city and city in desc):
                    title = _wikidata_sitelink(e.get("id"), lang)
                    if title:
                        return title
            return None
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < retries:
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    ra = min(float(ra), 30.0) if ra else 8.0
                except (TypeError, ValueError):
                    ra = 8.0
                time.sleep(ra + 0.5)
            elif attempt < retries:
                time.sleep(min(6.0, 1.0 * (2 ** attempt)) + 0.2)
        except Exception as err:
            last_err = err
            if attempt < retries:
                time.sleep(min(6.0, 1.0 * (2 ** attempt)) + 0.2)
    print(f"  [warn] Wikidata 检索失败 {term!r}: {last_err}")
    return None


def _name_hit(spot_name: str, title: str, extract: str) -> bool:
    """景点名是否被维基条目命中（名称驱动）.

    采信：
      - 核心名出现在正文，或核心名出现在标题（强信号）；
      - 标题是核心名的子串（弱信号，容忍品牌名变体，如「喜家德」∈「喜家德虾仁水饺」），
        但通用词（博物馆/火锅/酒店…）即使作为子串也不采信，避免把通用词条错挂到具体 POI；
      - 空标题不参与匹配（避免 '' in core 误判为命中）。
    """
    core = _core_name(spot_name)
    if not core:
        return False
    t = title or ""
    if not t:
        return False
    if core in (extract or "") or core in t:
        return True
    # 弱匹配：标题是核心名的子串（品牌名变体），但通用词子串不采信
    if len(t) >= 2 and t not in GENERIC_SUFFIXES and t in core:
        return True
    return False


# 行政区后缀：用于判断「城市是否以行政区形式明确出现在正文」
# （排除『中山』⊂『孫中山』这类仅作为人名一部分的误匹配）
ADMIN_SUFFIXES = ("市", "区", "县", "省", "州", "盟", "新区", "地区")


# 陷阱城市：城市名是某人名的子串（『中山』⊂『孫中山/孙中山』），
# 不能仅用「城市出现在正文」判定，必须靠行政区形式（『中山市』）或标题以城市开头。
TRAP_CITIES = ("中山",)


def _is_enumeration(extract: str, core: str) -> bool:
    """正文是否在枚举多个城市同名实例（如『人民公园 (上海市) 人民公园 (重庆市)…』）。

    通用概念/消歧列表页不是针对本城市的具体条目，应拒绝。判别：正文反复出现
    『core (城市)』式列举（全角/半角括号均可）>=4 次，远超具体条目通常只点名
    1~2 次的情况。
    """
    if not extract or not core:
        return False
    cnt = extract.count(core + " (") + extract.count(core + " （")
    return cnt >= 4


def _city_scoped(city: str, title: str, extract: str, core: str) -> bool:
    """泛化公共地名是否真是『该城市的那个实例』（而非通用概念页/跨城同名）。

    采信信号（任一满足即视为城市专属条目）：
      1) 行政区形式点名城市（最严格）：lede 含『兰州市』『中山市』『乌鲁木齐市』…
         —— 排除通用概念页仅在举例列表里带出『乌鲁木齐人民公园』的情况，
            也排除『中山』⊂『孫中山』的误匹配；
      2) 标题以城市开头（城市专属条目）：『乌鲁木齐人民公园』『上海世博会博物馆』；
         —— 陷阱城市（中山）的通用概念页也以城市开头（『中山公園』），故排除；
      3) 城市在 lede 极早期（前 80 字）作为实体所在地出现：『北京故宮』『哈尔滨市中央大街』；
         —— 排除通用概念页把城市放在举例列表末尾的情况；陷阱城市仍排除。
    否决：正文是『多城市同名实例枚举页』（如人民公园罗列几十个城市）——不是具体条目。
    """
    if not city:
        return False
    if _is_enumeration(extract or "", core):
        return False
    lede = (extract or "")[:500]
    # 1) 行政区形式点名城市（最严格）
    if any(city + suf in lede for suf in ADMIN_SUFFIXES):
        return True
    # 2) 标题以城市开头（城市专属条目）；陷阱城市排除
    if (title or "").startswith(city) and city not in TRAP_CITIES:
        return True
    # 3) 城市在 lede 前 80 字作为实体所在地；陷阱城市 / 2字陷阱仍排除
    early = (extract or "")[:80]
    if city in early and (len(city) >= 3 or city not in TRAP_CITIES):
        return True
    return False


def _is_relevant(spot_name: str, city: str, title: str, extract: str) -> bool:
    """相关性/消歧判定（名称驱动，严格版）.

    采信条件：
      - 标题为消歧义页，或正文以「X可以指」开头（消歧义页）-> 拒绝（无实质内容）；
      - 泛化公共地名（公园/广场/酒店/博物馆…）-> 必须是『城市专属』条目：
        标题含城市，或正文 lede 以行政区形式点名城市（『兰州市』『中山市』…），
        否则视为通用概念页/跨城同名，拒绝（避免把『人民公园』通用概念错挂到具体城市 POI）；
      - 其余（品牌/餐厅/酒店等专名）-> 名称驱动：核心名须命中标题/正文，否则拒绝兜底垃圾。
    """
    if not city:
        return _name_hit(spot_name, title, extract)
    core = _core_name(spot_name)
    # 消歧义 / 同名列举页（『X，可以指：』『X，可能是指：』）无实质内容，直接拒绝
    head = (extract or "")[:80]
    if "消歧义" in (title or "") or "可以指" in head or "可能是指" in head:
        return False
    # 泛化公共地名：跨城同名，必须是城市专属条目才采信（置于名称命中之前）
    if any(core.endswith(s) for s in GENERIC_SUFFIXES):
        return _city_scoped(city, title, extract, core)
    return _name_hit(spot_name, title, extract)


def _is_junk(name: str) -> bool:
    """过滤测试/垃圾 POI（E2E、Test、测试、demo 等无意义条目）."""
    n = (name or "").lower()
    return any(k in n for k in ("e2e", "test", "测试", "demo", "xxx"))


def _select_targets(spots: List[Dict[str, Any]], limit: Optional[int]) -> List[Dict[str, Any]]:
    """抽样策略：剔除测试/垃圾 POI → 按评分降序 → 去重 → 截断到 limit。"""
    seen = set()
    real = []
    for s in spots:
        name = s.get("name")
        if not name or _is_junk(name):
            continue
        if name in seen:
            continue
        seen.add(name)
        real.append(s)
    real.sort(key=lambda s: (s.get("rating") or 0), reverse=True)
    return real[:limit] if limit else real


async def fetch_city(
    city: str,
    spots: List[Dict[str, Any]],
    lang: str,
    limit: Optional[int],
    sleep: float,
    concurrency: int = 10,
    use_wikidata: bool = True,
    max_candidates: int = 3,
) -> List[Dict[str, Any]]:
    """抓取单个城市的景点维基词条. 并发（信号量限流）以缩短整体耗时."""
    out: List[Dict[str, Any]] = []
    targets = _select_targets(spots, limit)
    sem = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    async def _one(spot):
        name = spot.get("name")
        if not name:
            return None
        # S1 修正：先用完整景点名（不剥城市前缀），失败再退回「剥城市前缀」版本。
        # 避免「丽江古城」被误剥成「古城」→ 错挂到「中国四大古城」列举页；
        # 而「拉萨布达拉宫」靠搜索子串重叠仍能落到「布达拉宫」。
        term_full = _core_name(name)
        term_stripped = _query_term(name, city)
        terms = [t for t in (term_full, term_stripped) if t]
        async with sem:
            res = None
            for term in terms:
                if res and _is_relevant(name, city, res["title"], res["extract"]):
                    break
                # 1) 精确标题
                try:
                    r = await loop.run_in_executor(None, _api_query, lang, term)
                except Exception:
                    r = None
                if r and _is_relevant(name, city, r["title"], r["extract"]):
                    res = r
                    break
                # 2) 模糊检索兜底（追加城市名提升召回）
                try:
                    r2 = await loop.run_in_executor(None, _search_query, lang, term, name, city, 3, max_candidates)
                except Exception:
                    r2 = None
                if r2 and _is_relevant(name, city, r2["title"], r2["extract"]):
                    res = r2
                    break
                # 3) Wikidata 实体兜底（景点名↔维基条目别名/跨语言匹配；可关闭以规避限流）
                wtitle = None
                if use_wikidata:
                    try:
                        wtitle = await loop.run_in_executor(None, _wikidata_search, lang, term, city)
                    except Exception:
                        wtitle = None
                if wtitle:
                    try:
                        r3 = await loop.run_in_executor(None, _api_query, lang, wtitle)
                    except Exception:
                        r3 = None
                    if r3 and _is_relevant(name, city, r3["title"], r3["extract"]):
                        res = r3
                        break
            if res and _is_relevant(name, city, res["title"], res["extract"]):
                return {
                    "spot_name": name,
                    "city": city,
                    "title": res["title"],
                    "extract": res["extract"],
                    "pageid": res["pageid"],
                    "source_url": res["source_url"],
                    "lang": lang,
                }
            return None

    tasks = [_one(s) for s in targets]
    done = 0
    total_t = len(tasks)
    for coro in asyncio.as_completed(tasks):
        r = await coro
        if r:
            out.append(r)
        done += 1
        if sleep and sleep > 0:
            await asyncio.sleep(sleep)
        if done % 50 == 0:
            print(f"  {city} 进度 {done}/{total_t}（已命中 {len(out)}）")
    print(f"  {city}: {len(out)}/{len(targets)} 命中")
    return out


async def main_async(args):
    """M3-A 改造后：入队 fetch_city_wiki job，worker 异步消费。

    流程：
    1. 加载城市列表（--from-mysql 走 MySQL / 否则走 SPOTS_DIR 快照）
    2. --skip-existing 预过滤（主进程读 wiki_raw/{city}.json 是否存在）
    3. 逐城入队 fetch_city_wiki job（job_id = f"wiki_fetch:{city}" 幂等）
    4. 等所有 job 完成（Job.result 轮询 Redis）
    5. 打印 summary

    降级行为：Redis 不可用时 task_queue 走 asyncio.create_task 内存模式，
    主进程自己跑 fetch_city_wiki（不跨进程，单机调试用）。
    """
    from src.services.task_queue import get_task_queue
    from src.services.tasks.wiki_fetch import fetch_city_wiki
    from src.config.settings import settings
    from arq import create_pool
    from arq.connections import RedisSettings

    os.makedirs(WIKI_RAW_DIR, exist_ok=True)

    # 主进程自己持有 arq pool（用来 await job.result()）
    # task_queue 单例也会用这个 pool
    pool = None
    try:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        tq = get_task_queue()
        if not tq.is_arq:
            tq.attach_arq_pool(pool)
        print("[fetch_wiki] arq pool 已建立（Redis 可用，job 由 worker 进程消费）")
        print("提示：另开终端跑 worker: cd trip-backend && .venv/bin/python worker.py")
    except Exception as e:
        print(f"⚠️ Redis 不可用：{e}，降级为 asyncio 模式（主进程直接跑，仅本地调试用）")

    # ── S1：数据库对齐模式 ──
    # 直接遍历产品库真实景点（30792 个），而非 data/spots 那个餐饮为主的快照，
    # 这才是覆盖率真正的杠杆。产出 wiki_raw/{city}.json 后，既有 ingest_spot_docs.py
    # 会按 (name, city) 自动关联到正确 spot_id，无需改动摄取端。
    if args.from_mysql:
        sys.path.insert(0, ROOT)
        from sqlalchemy import select as _sa_select
        from src.config.database import async_session
        # 全量模型导入：确保 SQLAlchemy 配置 mapper 时能解析所有关系
        # （例如 User -> TokenUsageLog），否则首次建 session 会抛 InvalidRequestError。
        import src.models.user  # noqa: F401
        import src.models.conversation  # noqa: F401
        import src.models.message  # noqa: F401
        import src.models.trip  # noqa: F401
        import src.models.spot  # noqa: F401
        import src.models.spot_doc  # noqa: F401
        import src.models.password_reset  # noqa: F401
        import src.models.role  # noqa: F401
        import src.models.feedback  # noqa: F401
        import src.models.agent_step  # noqa: F401
        import src.models.token_usage_log  # noqa: F401
        from src.models.spot import Spot

        async with async_session() as db:
            q = _sa_select(Spot.name, Spot.city).where(
                Spot.city.isnot(None), Spot.city != ""
            )
            if args.city:
                q = q.where(Spot.city == args.city)
            rows = (await db.execute(q)).all()
        city_spots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for name, city in rows:
            if name:
                city_spots[city].append({"name": name, "city": city})
        if not city_spots:
            print("MySQL 中未查询到任何带城市的景点")
            return
        total_cities = len(city_spots)
        total_spots = sum(len(v) for v in city_spots.values())
        print(f"MySQL 对齐模式：共 {total_cities} 城 / {total_spots} 个真实景点")

        # M3-A 改造：跨城循环改成入队 fetch_city_wiki job
        # - 预过滤 skip-existing（主进程读 wiki_raw/{city}.json 跳过已写）
        # - 逐城入队（job_id 幂等 f"wiki_fetch:{city}"）
        # - 等所有 job 完成（Job.result 轮询 Redis）
        # - 写文件由 worker 端 fetch_city_wiki 自己完成
        from src.services.task_queue import get_task_queue
        tq = get_task_queue()

        if args.skip_existing:
            before = len(city_spots)
            city_spots = {c: s for c, s in city_spots.items()
                          if not os.path.exists(os.path.join(WIKI_RAW_DIR, c + ".json"))}
            skipped = before - len(city_spots)
            if skipped:
                print(f"  --skip-existing：跳过 {skipped} 城已存在 wiki_raw/{{city}}.json")

        if not city_spots:
            print("MySQL 对齐模式：无剩余城市可处理")
            return

        print(f"入队 {len(city_spots)} 个 fetch_city_wiki job...")
        from arq.jobs import Job
        job_specs = []
        for city in city_spots.keys():
            job_id = f"wiki_fetch:{city}"
            await tq.enqueue(
                fetch_city_wiki,
                city=city, lang=args.lang, limit=args.limit, sleep=args.sleep,
                concurrency=args.concurrency, use_wikidata=not args.no_wikidata,
                max_candidates=args.max_candidates, from_db=True,
                job_id=job_id,
            )
            job_specs.append((city, job_id))

        # 等完成（2h 上限）
        if pool is None:
            # asyncio 降级：fetch_city_wiki 已写文件
            total_fetched = 0
            for city, _ in job_specs:
                out_path = os.path.join(WIKI_RAW_DIR, city + ".json")
                if os.path.exists(out_path):
                    with open(out_path) as fh:
                        total_fetched += len(json.load(fh))
            print(f"MySQL 对齐模式：完成（asyncio 降级）共 fetched {total_fetched} 条")
            return

        total_fetched = 0
        total_errors = 0
        for city, job_id in job_specs:
            try:
                raw = await Job(job_id, redis=pool).result(timeout=7200)
                actual = raw.get("r") if isinstance(raw, dict) and "r" in raw else raw
                if isinstance(actual, dict):
                    total_fetched += actual.get("fetched", 0)
                print(f"  ✓ {city}: {actual.get('fetched', 0)}/{actual.get('total_spots', 0)} 命中")
            except Exception as e:
                total_errors += 1
                print(f"  ❌ {city}: {e}")

        print(f"MySQL 对齐模式：完成 {len(job_specs)} 城，fetched {total_fetched} 条，{total_errors} 城失败")
        if pool is not None:
            await pool.aclose() if hasattr(pool, "aclose") else await pool.close()
        return

    # ── 原有快照模式 ──
    city_files = sorted(f for f in os.listdir(SPOTS_DIR) if f.endswith(".json"))
    if args.city:
        city_files = [f for f in city_files if f[:-5] == args.city]
    if not city_files:
        print(f"未找到城市文件（SPOTS_DIR={SPOTS_DIR}）")
        return

    # M3-A 改造：跨城循环改成入队（与 MySQL 模式同套路）
    from src.services.task_queue import get_task_queue
    tq = get_task_queue()

    target_cities = [cf[:-5] for cf in city_files]
    if args.skip_existing:
        before = len(target_cities)
        target_cities = [
            c for c in target_cities
            if not os.path.exists(os.path.join(WIKI_RAW_DIR, c + ".json"))
        ]
        skipped = before - len(target_cities)
        if skipped:
            print(f"  --skip-existing：跳过 {skipped} 城已存在 wiki_raw/{{city}}.json")

    if not target_cities:
        print("快照模式：无剩余城市可处理")
        return

    print(f"入队 {len(target_cities)} 个 fetch_city_wiki job（snapshot 模式）...")
    from arq.jobs import Job
    job_specs = []
    for city in target_cities:
        job_id = f"wiki_fetch:{city}"
        await tq.enqueue(
            fetch_city_wiki,
            city=city, lang=args.lang, limit=args.limit, sleep=args.sleep,
            concurrency=args.concurrency, use_wikidata=not args.no_wikidata,
            max_candidates=args.max_candidates, from_db=False,
            job_id=job_id,
        )
        job_specs.append((city, job_id))

    # 等完成
    if pool is None:
        total_fetched = 0
        for city, _ in job_specs:
            out_path = os.path.join(WIKI_RAW_DIR, city + ".json")
            if os.path.exists(out_path):
                with open(out_path) as fh:
                    total_fetched += len(json.load(fh))
        print(f"快照模式：完成（asyncio 降级）共 fetched {total_fetched} 条")
        return

    total_fetched = 0
    total_errors = 0
    for city, job_id in job_specs:
        try:
            raw = await Job(job_id, redis=pool).result(timeout=7200)
            actual = raw.get("r") if isinstance(raw, dict) and "r" in raw else raw
            if isinstance(actual, dict):
                total_fetched += actual.get("fetched", 0)
            print(f"  ✓ {city}: {actual.get('fetched', 0)}/{actual.get('total_spots', 0)} 命中")
        except Exception as e:
            total_errors += 1
            print(f"  ❌ {city}: {e}")

    print(f"快照模式：完成 {len(job_specs)} 城，fetched {total_fetched} 条，{total_errors} 城失败")
    if pool is not None:
        await pool.aclose() if hasattr(pool, "aclose") else await pool.close()


def main():
    p = argparse.ArgumentParser(description="抓取维基百科词条（文本层 ETL）")
    p.add_argument("--city", help="只抓取指定城市")
    p.add_argument("--limit", type=int, help="每城最多抓取 N 个景点（抽样验证用）")
    p.add_argument("--lang", default="zh", choices=["zh", "en"], help="维基语言")
    p.add_argument("--sleep", type=float, default=0.02, help="每任务完成后额外间隔（秒）")
    p.add_argument("--concurrency", type=int, default=10, help="并发请求数（默认 10）")
    p.add_argument("--skip-existing", action="store_true",
                   help="跳过已存在 wiki_raw/{city}.json 的城市（仅回填缺失城市）")
    p.add_argument("--from-mysql", action="store_true",
                   help="S1：直接遍历 MySQL 真实景点（而非 data/spots 快照）生成 wiki_raw，覆盖全部 30792 景点")
    p.add_argument("--no-wikidata", action="store_true",
                   help="S1：关闭 Wikidata 实体兜底（规避维基限流 429，批量抓取用）")
    p.add_argument("--max-candidates", type=int, default=3,
                   help="模糊检索每层最多取前 N 个候选抽正文（默认 3，降低 miss 成本）")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
