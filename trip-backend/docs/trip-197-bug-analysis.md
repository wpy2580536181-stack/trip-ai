# 行程规划 Bug 排查报告

## 问题描述

行程 ID=197 存在以下严重问题：
1. **第一天**：上午和下午都是天安门
2. **第一天晚上**：景点是全聚德（明显是餐饮）
3. **第二天**：上午和下午都是故宫
4. **第三天**：出现两个天安门

---

## 根本原因分析

### 🔴 Bug 1：封闭世界约束从未生效

**文件**：`trip-backend/src/services/agent/agents/planner_agent.py` 第 142-151 行

```python
# 封闭世界约束（候选池中的景点名列表）
if input.bundle:
    spot_names = input.bundle.all_spot_names()
    if spot_names:
        # ... 注入 prompt
```

**问题**：`ResearchBundle.all_spot_names()` 返回空集合，导致约束从未注入。

**原因链**：
- `ResearchBundle.attraction_items` 和 `food_items` 初始化为空列表 `[]`
- `ResearchAgent._parallel_search()` 第 300-306 行创建 `ResearchBundle` 时，**只传入了字符串字段**（`attractions`, `food`, `hotels`），未填充结构化字段
- `all_spot_names()` 遍历两个空列表，返回 `set()`
- Planner 的封闭世界约束条件判断 `if spot_names:` 为 `False`，**不注入约束**

**影响**：Planner LLM 不受候选池限制，可自由使用任何景点名称（包括重复、错误分类）。

---

### 🔴 Bug 2：Planner Prompt 缺少去重约束

**文件**：`trip-backend/src/services/agent/planner_prompt.py`

**现状**：
- Prompt 仅定义了 JSON 字段结构
- **没有明确要求"不同天不重复景点"**
- **没有明确要求"上午/下午/晚上时段禁止填入餐饮"**
- 仅对 `accommodation` 字段加了"禁止填入餐饮"约束（第 129 行）

**结果**：LLM 可自由分配景点，导致：
- 同一景点出现在多天
- 餐饮（如全聚德）被填入 `evening.spot`

---

### 🔴 Bug 3：代码层缺乏全量去重校验

**相关文件**：
1. `trip-backend/src/services/agent/patch_engine.py` 第 60-70 行
2. `trip-backend/src/services/trip_service.py` 第 469-498 行

**patch_engine._validate_no_duplicate()**：
```python
def _validate_no_duplicate(itinerary: list, day: int, new_spot: str, exclude_period: Optional[str] = None) -> None:
    """检查同一天内是否有重复景点（跨时段去重）。"""
    for d in itinerary:
        if d.get("day") != day:
            continue
        for period in ("morning", "afternoon", "evening"):
            # ...
```
- **仅用于 patch 操作的局部修改**
- **不适用于全量行程生成**

**trip_service._validate_and_fix_trip_data()**：
```python
# 仅检查 accommodation
slot = day.get("accommodation")
```
- **只检查住宿字段**，未检查 morning/afternoon/evening
- 对餐饮字段的检测仅限于住宿时段

**review.py** 第 107 行：
```python
if bundle and bundle.all_spot_names():
    code_checks["pool_compliance"] = "skipped_phase1"
```
- 候选池合规检查被**明确跳过**（标记为 `skipped_phase1`）

---

### 🟡 Bug 4：候选池数据分离不彻底

**文件**：`trip-backend/src/services/agent/planner_prompt.py` 第 29-49 行

```python
def _format_bundle(bundle: dict) -> str:
    lines = []
    if bundle.get("attractions"):
        lines.append(f"## 景点信息\n{bundle['attractions']}")
    if bundle.get("food"):
        lines.append(f"## 美食信息\n{bundle['food']}")  # ← 美食混入
    # ...
```

**问题**：虽然 `retrieve_knowledge_tool` 返回时区分了 `category="attraction"` 和 `category="food"`，但 `_format_bundle()` 将**景点和美食文本一起注入 prompt**，LLM 难以严格区分哪些名称是景点、哪些是美食。

---

## 问题成因总结

| 问题 | 根因 | 严重性 |
|------|------|--------|
| 同景点重复出现 | 1. 封闭世界约束无效<br>2. Prompt 无去重要求<br>3. 无代码层去重 | 🔴 高 |
| 餐饮进入景点时段 | 1. 时段约束缺失<br>2. 仅 accommodation 有检测<br>3. 美食文本混入 prompt | 🔴 高 |
| 跨天重复 | 完全没有跨天去重逻辑 | 🔴 高 |

---

## 修复建议

### 优先级 1：立即修复（阻断性问题）

#### 1.1 修复封闭世界约束

**文件**：`trip-backend/src/services/agent/agents/research_agent.py`

**方案 A（推荐）**：解析 `retrieve_knowledge_tool` 返回的文本，提取 POI 名称填充 `attraction_items`/`food_items`

```python
# 在 _parallel_search 方法末尾
from src.services.agent.schemas import SpotItem

def _extract_spot_items(text: str, category: str) -> list[SpotItem]:
    """从 RAG 返回文本中提取 POI 名称（简化版）。"""
    items = []
    # 解析逻辑：按行分割，提取 "名称：xxx" 格式
    for line in text.split('\n'):
        if '：' in line or ':' in line:
            name_part = line.split('：', 1)[0].split(':', 1)[0].strip()
            if name_part and len(name_part) < 20:
                items.append(SpotItem(name=name_part, category=category))
    return items[:10]  # 最多取 10 个

# 在创建 ResearchBundle 前
attr_items = _extract_spot_items(bundle_data.get("attractions", ""), "attraction")
food_items = _extract_spot_items(bundle_data.get("food", ""), "food")

return ResearchBundle(
    attractions=bundle_data.get("attractions"),
    food=bundle_data.get("food"),
    hotels=bundle_data.get("hotels"),
    weather=bundle_data.get("weather"),
    distance=bundle_data.get("distance"),
    attraction_items=attr_items,   # ← 新增
    food_items=food_items,          # ← 新增
)
```

#### 1.2 强化 Planner Prompt 去重约束

**文件**：`trip-backend/src/services/agent/planner_prompt.py`

在 `build_planner_prompt()` 的"输出格式"部分后添加：

```python
# 景点去重（CRITICAL）
parts.append("""
# 景点去重（CRITICAL）
- **绝对禁止**将同一景点分配到多天（如 Day 1 和 Day 3 都出现"天安门"）
- **绝对禁止**在同一天内多次使用同一景点（如上午和下午都是"故宫"）
- 上午/下午/晚上（morning/afternoon/evening）时段只能填入**景点或文化活动**，禁止填入餐饮（餐厅、烤鸭店等）
- 餐饮必须填入 breakfast/lunch/dinner 时段，不能填入 morning/afternoon/evening
""")
```

---

### 优先级 2：代码层强化校验

#### 2.1 增加全量行程去重检查

**文件**：`trip-backend/src/services/trip_service.py`

在 `_validate_and_fix_trip_data()` 中增加：

```python
@staticmethod
def _validate_and_fix_trip_data(parsed: dict) -> None:
    # ... 现有 accommodation 校验 ...

    # 新增：全量去重检查
    spot_usage: dict[str, list[int]] = {}  # spot_name -> [day1, day2, ...]
    _FOOD_KEYWORDS = ("烤鸭", "餐厅", "餐馆", "饭店", "火锅", "小吃", "面", "饭", "菜", "食", "茶", "咖啡", "bar", "cafe", "restaurant")

    for day in daily_itinerary:
        day_num = day.get("day", 0)
        for period in ("morning", "afternoon", "evening"):
            slot = day.get(period)
            if not slot or not slot.get("spot"):
                continue
            spot_name = slot["spot"]

            # 检查是否为餐饮进入景点时段
            lower = spot_name.lower()
            if any(kw in lower for kw in _FOOD_KEYWORDS):
                trip_log.warning(
                    "food_in_attraction_slot",
                    day=day_num, period=period, spot=spot_name,
                    action="cleared"
                )
                slot["spot"] = ""
                slot["description"] = "景点信息待确认"
                continue

            # 跨天去重
            if spot_name in spot_usage:
                spot_usage[spot_name].append(day_num)
                trip_log.warning(
                    "duplicate_spot_across_days",
                    spot=spot_name, days=spot_usage[spot_name],
                    action="cleared_later"
                )
                # 清空后续重复出现的该景点
                slot["spot"] = ""
                slot["description"] = "景点信息待确认"
            else:
                spot_usage[spot_name] = [day_num]
```

#### 2.2 重新启用审阅阶段的候选池合规检查

**文件**：`trip-backend/src/services/agent/review.py` 第 106-110 行

```python
# ── Step 5: 候选池合规（封闭世界校验）──
if bundle and bundle.all_spot_names():
    pool_names = bundle.all_spot_names()
    # 提取行程中所有景点名
    trip_spots = set()
    for day in itinerary:
        for period in ("morning", "afternoon", "evening"):
            slot = day.get(period)
            if slot and slot.get("spot"):
                trip_spots.add(slot["spot"])
    # 检查是否有候选池外的景点
    unknown = trip_spots - pool_names
    if unknown:
        code_checks["pool_compliance"] = False
        issue = f"以下景点不在候选池中：{unknown}"
        return parsed, ReviewResult(
            passed=False,
            issues=[issue],
            feedback=f"请仅使用候选池中的景点。未知景点：{unknown}",
            code_checks=code_checks,
        )
    code_checks["pool_compliance"] = True
else:
    code_checks["pool_compliance"] = "no_pool"
```

---

## 验证方案

修复后，应对以下场景进行测试：

### 测试用例 1：封闭世界约束
- **输入**：候选池包含【天安门、故宫、颐和园】
- **期望**：生成行程仅使用这三个景点，不使用其他景点

### 测试用例 2：跨天去重
- **输入**：3 天行程，候选池充足
- **期望**：每个景点最多出现 1 次

### 测试用例 3：时段隔离
- **输入**：3 天行程，候选池包含景点【故宫】和美食【全聚德】
- **期望**：
  - `morning/afternoon/evening` 只出现【故宫】
  - `dinner` 时段可能出现【全聚德】
  - `evening.spot` 绝不出【全聚德】

---

## 总结

**核心病因**：
1. **封闭世界约束失效**（候选池未结构化填充）
2. **Prompt 缺乏去重和时段隔离约束**
3. **代码层无全量去重校验**

**修复路径**：
1. ✅ **短期**：强化 Prompt + 增加 `_validate_and_fix_trip_data()` 去重逻辑
2. ✅ **中期**：修复 `ResearchBundle` 结构化填充，重新启用审阅合规检查
3. ✅ **长期**：引入基于向量的景点相似度检测（防止"故宫"和"故宫博物院"被判定为不同景点）

---

*报告生成时间：2026-08-01*
*代码版本：3bb4841（三个行程展示bug修复 + 地理编码命中率提升至65%）*
