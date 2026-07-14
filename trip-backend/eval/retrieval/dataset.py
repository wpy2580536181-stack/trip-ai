"""
检索层评估数据集。

包含 ~15 个标杆景点（覆盖 8 城市 × 3 类别），
每个景点配 3~5 条自然语言 query。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RetrievalTestCase:
    """一条检索测试用例"""
    query: str
    gold_spot_id: int
    gold_spot_name: str
    gold_city: str
    gold_category: str
    query_type: str          # direct / feature / need / vague / mixed


@dataclass
class Spot:
    """测试景点"""
    id: int
    name: str
    city: str
    category: str
    description: str
    tags: list[str] = field(default_factory=list)
    rating: float = 4.0
    avg_cost: Optional[float] = None


# ──────────────────────────────────────────────
# 测试景点数据（15 个标杆景点）
# ──────────────────────────────────────────────

SPOTS: list[Spot] = [
    # ── 北京 ──
    Spot(id=1, name="故宫博物院", city="北京", category="景点",
         description="明清两代的皇家宫殿，世界文化遗产，位于北京中轴线的中心",
         tags=["历史", "文化", "古建筑"], rating=4.8, avg_cost=60),
    Spot(id=2, name="全聚德烤鸭", city="北京", category="美食",
         description="中华老字号，以挂炉烤鸭闻名，外酥里嫩",
         tags=["美食", "烤鸭", "老字号"], rating=4.5, avg_cost=200),
    Spot(id=3, name="八达岭长城", city="北京", category="景点",
         description="明代长城最著名段落，世界文化遗产，位于北京延庆区",
         tags=["自然", "历史", "户外"], rating=4.7, avg_cost=40),

    # ── 成都 ──
    Spot(id=4, name="宽窄巷子", city="成都", category="景点",
         description="成都保存最完好的清朝古街区，含宽巷子、窄巷子、井巷子三条平行古街",
         tags=["古街", "文化", "美食"], rating=4.4, avg_cost=0),
    Spot(id=5, name="大熊猫繁育研究基地", city="成都", category="景点",
         description="世界著名的大熊猫保护研究机构，可近距离观察大熊猫",
         tags=["动物", "亲子", "自然"], rating=4.7, avg_cost=55),
    Spot(id=6, name="陈麻婆豆腐", city="成都", category="美食",
         description="中华老字号川菜馆，麻婆豆腐创始店，麻辣鲜香",
         tags=["川菜", "美食", "老字号"], rating=4.3, avg_cost=80),

    # ── 西安 ──
    Spot(id=7, name="秦始皇兵马俑博物馆", city="西安", category="景点",
         description="世界第八大奇迹，秦始皇陵陪葬坑出土的数千件陶俑",
         tags=["历史", "考古", "文化"], rating=4.8, avg_cost=120),
    Spot(id=8, name="回民街", city="西安", category="美食",
         description="西安最著名的小吃街，汇集西北及穆斯林特色美食",
         tags=["美食", "小吃", "夜市"], rating=4.2, avg_cost=60),

    # ── 杭州 ──
    Spot(id=9, name="西湖", city="杭州", category="景点",
         description="世界文化遗产，中国十大风景名胜之一，含断桥、雷峰塔等十景",
         tags=["自然", "湖景", "文化"], rating=4.7, avg_cost=0),
    Spot(id=10, name="楼外楼", city="杭州", category="美食",
         description="百年老店，正宗杭帮菜，西湖醋鱼、东坡肉为招牌",
         tags=["美食", "杭帮菜", "老字号"], rating=4.4, avg_cost=180),

    # ── 上海 ──
    Spot(id=11, name="外滩", city="上海", category="景点",
         description="上海的标志性景观带，汇集万国建筑博览群，对岸为陆家嘴金融区",
         tags=["都市", "夜景", "文化"], rating=4.6, avg_cost=0),

    # ── 三亚 ──
    Spot(id=12, name="亚龙湾", city="三亚", category="景点",
         description="天下第一湾，拥有 7 公里长的银白色沙滩和清澈海水",
         tags=["海滩", "度假", "自然"], rating=4.6, avg_cost=0),

    # ── 丽江 ──
    Spot(id=13, name="丽江古城", city="丽江", category="景点",
         description="世界文化遗产，茶马古道上的纳西族古城，小桥流水人家",
         tags=["古城", "文化", "慢生活"], rating=4.5, avg_cost=0),

    # ── 桂林 ──
    Spot(id=14, name="漓江", city="桂林", category="景点",
         description="桂林山水甲天下，漓江百里画廊，典型的喀斯特地貌风光",
         tags=["自然", "山水", "游船"], rating=4.7, avg_cost=300),
    Spot(id=15, name="桂林米粉", city="桂林", category="美食",
         description="桂林最具代表性的地方小吃，以卤水米粉闻名，历史悠久",
         tags=["美食", "小吃", "特色"], rating=4.3, avg_cost=15),
]


# ──────────────────────────────────────────────
# 测试 Query（每个景点 4 条）
# ──────────────────────────────────────────────

QUERIES: list[RetrievalTestCase] = [
    # 故宫 (id=1)
    RetrievalTestCase(query="北京故宫怎么玩", gold_spot_id=1, gold_spot_name="故宫博物院",
                       gold_city="北京", gold_category="景点", query_type="vague"),
    RetrievalTestCase(query="介绍北京的皇家宫殿", gold_spot_id=1, gold_spot_name="故宫博物院",
                       gold_city="北京", gold_category="景点", query_type="feature"),
    RetrievalTestCase(query="北京哪里能看明清古建筑", gold_spot_id=1, gold_spot_name="故宫博物院",
                       gold_city="北京", gold_category="景点", query_type="need"),
    RetrievalTestCase(query="故宫的门票多少钱", gold_spot_id=1, gold_spot_name="故宫博物院",
                       gold_city="北京", gold_category="景点", query_type="direct"),

    # 全聚德 (id=2)
    RetrievalTestCase(query="北京吃烤鸭去哪里", gold_spot_id=2, gold_spot_name="全聚德烤鸭",
                       gold_city="北京", gold_category="美食", query_type="need"),
    RetrievalTestCase(query="全聚德烤鸭好吃吗", gold_spot_id=2, gold_spot_name="全聚德烤鸭",
                       gold_city="北京", gold_category="美食", query_type="direct"),
    RetrievalTestCase(query="北京有什么老字号餐厅", gold_spot_id=2, gold_spot_name="全聚德烤鸭",
                       gold_city="北京", gold_category="美食", query_type="feature"),
    RetrievalTestCase(query="推荐北京特色美食餐厅", gold_spot_id=2, gold_spot_name="全聚德烤鸭",
                       gold_city="北京", gold_category="美食", query_type="vague"),

    # 八达岭长城 (id=3)
    RetrievalTestCase(query="八达岭长城开放时间", gold_spot_id=3, gold_spot_name="八达岭长城",
                       gold_city="北京", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="北京有什么户外景点", gold_spot_id=3, gold_spot_name="八达岭长城",
                       gold_city="北京", gold_category="景点", query_type="feature"),
    RetrievalTestCase(query="带父母去北京爬长城推荐哪个", gold_spot_id=3, gold_spot_name="八达岭长城",
                       gold_city="北京", gold_category="景点", query_type="need"),

    # 宽窄巷子 (id=4)
    RetrievalTestCase(query="成都宽窄巷子有什么好玩的", gold_spot_id=4, gold_spot_name="宽窄巷子",
                       gold_city="成都", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="成都的古街推荐", gold_spot_id=4, gold_spot_name="宽窄巷子",
                       gold_city="成都", gold_category="景点", query_type="feature"),
    RetrievalTestCase(query="成都哪里既好玩又能吃美食", gold_spot_id=4, gold_spot_name="宽窄巷子",
                       gold_city="成都", gold_category="景点", query_type="mixed"),
    RetrievalTestCase(query="晚上去成都哪里逛", gold_spot_id=4, gold_spot_name="宽窄巷子",
                       gold_city="成都", gold_category="景点", query_type="vague"),

    # 大熊猫基地 (id=5)
    RetrievalTestCase(query="成都大熊猫基地在哪里", gold_spot_id=5, gold_spot_name="大熊猫繁育研究基地",
                       gold_city="成都", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="成都带孩子去哪里玩", gold_spot_id=5, gold_spot_name="大熊猫繁育研究基地",
                       gold_city="成都", gold_category="景点", query_type="need"),
    RetrievalTestCase(query="成都能看大熊猫的地方", gold_spot_id=5, gold_spot_name="大熊猫繁育研究基地",
                       gold_city="成都", gold_category="景点", query_type="feature"),

    # 陈麻婆豆腐 (id=6)
    RetrievalTestCase(query="成都最正宗的麻婆豆腐", gold_spot_id=6, gold_spot_name="陈麻婆豆腐",
                       gold_city="成都", gold_category="美食", query_type="feature"),
    RetrievalTestCase(query="成都吃川菜去哪里好", gold_spot_id=6, gold_spot_name="陈麻婆豆腐",
                       gold_city="成都", gold_category="美食", query_type="vague"),
    RetrievalTestCase(query="陈麻婆豆腐人均多少钱", gold_spot_id=6, gold_spot_name="陈麻婆豆腐",
                       gold_city="成都", gold_category="美食", query_type="direct"),

    # 兵马俑 (id=7)
    RetrievalTestCase(query="西安兵马俑值得去吗", gold_spot_id=7, gold_spot_name="秦始皇兵马俑博物馆",
                       gold_city="西安", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="西安有什么历史文化景点", gold_spot_id=7, gold_spot_name="秦始皇兵马俑博物馆",
                       gold_city="西安", gold_category="景点", query_type="feature"),
    RetrievalTestCase(query="世界第八大奇迹在哪里", gold_spot_id=7, gold_spot_name="秦始皇兵马俑博物馆",
                       gold_city="西安", gold_category="景点", query_type="vague"),

    # 回民街 (id=8)
    RetrievalTestCase(query="西安回民街有什么好吃的", gold_spot_id=8, gold_spot_name="回民街",
                       gold_city="西安", gold_category="美食", query_type="direct"),
    RetrievalTestCase(query="西安的小吃街推荐", gold_spot_id=8, gold_spot_name="回民街",
                       gold_city="西安", gold_category="美食", query_type="feature"),
    RetrievalTestCase(query="西安晚上去哪里吃夜市", gold_spot_id=8, gold_spot_name="回民街",
                       gold_city="西安", gold_category="美食", query_type="need"),

    # 西湖 (id=9)
    RetrievalTestCase(query="杭州西湖要门票吗", gold_spot_id=9, gold_spot_name="西湖",
                       gold_city="杭州", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="杭州必去的景点", gold_spot_id=9, gold_spot_name="西湖",
                       gold_city="杭州", gold_category="景点", query_type="vague"),
    RetrievalTestCase(query="杭州哪里看湖景", gold_spot_id=9, gold_spot_name="西湖",
                       gold_city="杭州", gold_category="景点", query_type="feature"),

    # 楼外楼 (id=10)
    RetrievalTestCase(query="杭州楼外楼的招牌菜", gold_spot_id=10, gold_spot_name="楼外楼",
                       gold_city="杭州", gold_category="美食", query_type="direct"),
    RetrievalTestCase(query="杭州吃正宗杭帮菜的餐厅", gold_spot_id=10, gold_spot_name="楼外楼",
                       gold_city="杭州", gold_category="美食", query_type="feature"),
    RetrievalTestCase(query="西湖边有什么老字号餐厅", gold_spot_id=10, gold_spot_name="楼外楼",
                       gold_city="杭州", gold_category="美食", query_type="need"),

    # 外滩 (id=11)
    RetrievalTestCase(query="上海外滩夜景怎么样", gold_spot_id=11, gold_spot_name="外滩",
                       gold_city="上海", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="上海必去的免费景点", gold_spot_id=11, gold_spot_name="外滩",
                       gold_city="上海", gold_category="景点", query_type="vague"),
    RetrievalTestCase(query="上海哪里看万国建筑", gold_spot_id=11, gold_spot_name="外滩",
                       gold_city="上海", gold_category="景点", query_type="feature"),

    # 亚龙湾 (id=12)
    RetrievalTestCase(query="三亚亚龙湾沙滩怎么样", gold_spot_id=12, gold_spot_name="亚龙湾",
                       gold_city="三亚", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="三亚哪个海滩最好", gold_spot_id=12, gold_spot_name="亚龙湾",
                       gold_city="三亚", gold_category="景点", query_type="feature"),
    RetrievalTestCase(query="三亚适合度假的海滩推荐", gold_spot_id=12, gold_spot_name="亚龙湾",
                       gold_city="三亚", gold_category="景点", query_type="need"),
    RetrievalTestCase(query="去三亚玩水去哪里", gold_spot_id=12, gold_spot_name="亚龙湾",
                       gold_city="三亚", gold_category="景点", query_type="vague"),

    # 丽江古城 (id=13)
    RetrievalTestCase(query="丽江古城好玩吗", gold_spot_id=13, gold_spot_name="丽江古城",
                       gold_city="丽江", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="云南有什么古镇推荐", gold_spot_id=13, gold_spot_name="丽江古城",
                       gold_city="丽江", gold_category="景点", query_type="vague"),
    RetrievalTestCase(query="丽江古城要门票吗", gold_spot_id=13, gold_spot_name="丽江古城",
                       gold_city="丽江", gold_category="景点", query_type="direct"),

    # 漓江 (id=14)
    RetrievalTestCase(query="桂林漓江游船多少钱", gold_spot_id=14, gold_spot_name="漓江",
                       gold_city="桂林", gold_category="景点", query_type="direct"),
    RetrievalTestCase(query="桂林山水哪里最美", gold_spot_id=14, gold_spot_name="漓江",
                       gold_city="桂林", gold_category="景点", query_type="vague"),
    RetrievalTestCase(query="桂林坐船看风景的地方", gold_spot_id=14, gold_spot_name="漓江",
                       gold_city="桂林", gold_category="景点", query_type="feature"),

    # 桂林米粉 (id=15)
    RetrievalTestCase(query="桂林米粉哪家正宗", gold_spot_id=15, gold_spot_name="桂林米粉",
                       gold_city="桂林", gold_category="美食", query_type="direct"),
    RetrievalTestCase(query="桂林有什么特色小吃", gold_spot_id=15, gold_spot_name="桂林米粉",
                       gold_city="桂林", gold_category="美食", query_type="feature"),
    RetrievalTestCase(query="桂林最出名的小吃", gold_spot_id=15, gold_spot_name="桂林米粉",
                       gold_city="桂林", gold_category="美食", query_type="vague"),
    RetrievalTestCase(query="桂林便宜又好吃的东西", gold_spot_id=15, gold_spot_name="桂林米粉",
                       gold_city="桂林", gold_category="美食", query_type="need"),
]


def get_spots_by_id(spot_id: int) -> Spot:
    """根据 ID 查找景点"""
    for s in SPOTS:
        if s.id == spot_id:
            return s
    raise KeyError(f"Spot id {spot_id} not found")


def build_spot_id_to_name() -> dict[int, str]:
    """构建 id -> name 映射"""
    return {s.id: s.name for s in SPOTS}


def dataset_summary() -> dict:
    """数据集概览统计"""
    cities = {}
    categories = {}
    query_types = {}

    for s in SPOTS:
        cities[s.city] = cities.get(s.city, 0) + 1
        categories[s.category] = categories.get(s.category, 0) + 1

    for q in QUERIES:
        query_types[q.query_type] = query_types.get(q.query_type, 0) + 1

    return {
        "total_spots": len(SPOTS),
        "total_queries": len(QUERIES),
        "queries_per_spot": len(QUERIES) / len(SPOTS),
        "cities": cities,
        "categories": categories,
        "query_types": query_types,
    }
