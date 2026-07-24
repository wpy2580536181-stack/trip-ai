---
name: local-life-discovery
description: "根据用户指定的地点，发现附近的好吃好玩好休息的地方。当用户询问某个位置周边的餐饮、娱乐、文化、休闲场所时主动使用——包括'附近有什么''周边推荐''XXX 附近''周围''离我近的'等说法。整合高德实时周边 POI 和知识库 RAG 检索，按分类分组输出推荐，每条包含距离和坐标信息。"
---

# Local Life Discovery Skill

发现用户指定地点附近的吃喝玩乐休闲场所。

## 核心流程

1. **解析地点坐标**：调用 `search_commute_tips_tool(keywords=地点名, city=城市)` 拿到候选坐标，选最匹配的。如果用户已经给出了具体坐标则跳过此步。

2. **并行数据获取**（三路召回）：

   a. **高德实时周边 POI**：调用 `search_nearby_commute_pois_tool(lat, lng, keywords=分类词, limit=15)`
      - 好吃：`keywords="餐饮"` 或 `keywords="美食"`
      - 好玩：`keywords="娱乐"` 或 `keywords="景点"` 或 `keywords="文化"`
      - 好休息：`keywords="咖啡馆"` 或 `keywords="书店"` 或 `keywords="公园"`

   b. **知识库 RAG 检索**：调用 `retrieve_knowledge_tool(query=地点+分类词, city=城市, category=对应类别)`
      - category 映射：好吃→"food"，好玩→"attraction"，好休息→"attraction"

3. **合并去重**：将两路结果合并，按名称去重（模糊匹配），保留有坐标的条目。

4. **分组输出**：按分类组织为以下结构：

   ```
   【好吃】
   1. 店名（距你 XXX 米）
      - 简介：...
      - 坐标：lat, lng
   
   2. ...
   
   【好玩】
   ...
   
   【好休息】
   ...
   ```

5. **每条数据必须包含**：名称、距离（米）、经纬度坐标、简介。这些信息用于前端地图标记。

## 注意事项

- 如果用户没给城市名，从地点名推断（如"人民广场"→上海，"天府广场"→成都），或在 search_commute_tips 中不传 city 让 API 返回全国候选
- 如果高德 POI 返回为空，降级为只查知识库
- 如果知识库也查不到，用高德 POI 结果即可，不要直接说"没有找到"
- 距离信息高德 POI 自带（distance 字段），知识库结果无距离信息则标注"未提供距离"
- 推荐数量控制在每类 5-8 条，避免信息过载
- 优先展示有坐标的条目（高德 POI 天然有坐标，知识库可能没有）

## 输入示例

```
用户：三里屯附近有什么好吃的
→ search_commute_tips("三里屯") → 坐标
→ search_nearby_pois(坐标, keywords="餐饮") + retrieve_knowledge("三里屯 美食", city="北京", category="food")
→ 合并分组输出
```

```
用户：成都东站附近适合休息的地方
→ search_commute_tips("成都东站", city="成都") → 坐标
→ search_nearby_pois(坐标, keywords="咖啡馆") + search_nearby_pois(坐标, keywords="书店") + search_nearby_pois(坐标, keywords="公园")
→ retrieve_knowledge("成都东站 附近 咖啡/书店", city="成都", category="attraction")
→ 合并分组输出
```
