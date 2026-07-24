---
name: route-optimize
description: "计算多出行方式下的最优通勤路线与逐步行程。当用户询问'怎么去''怎么走''最快路线''通勤时间''最优路线''驾车/公交/步行/骑行路线'并给出起终点时触发。支持驾车、公交、步行、骑行四种方式的横向对比，可输出逐步行程时间线和到达时刻估算。"
---

# 路线优化 Skill

## Trigger
用户意图包含「路线 / 通勤 / 怎么去 / 怎么走 / 最优路线 / 最快 / 通勤时间」并给出起终点时触发。

## Tools（L3 执行时可用）
- `search_commute_tips_tool(keywords, city?, limit?)`：按名称联想地点并返回候选坐标（地理编码辅助）。
- `compute_optimal_commute_tool(origin, destinations, mode, city?, compare_modes?)`：计算真实路网通勤并择优。
- `search_nearby_commute_pois_tool(lat, lng, radius?, keywords?, types?, limit?)`：查周边 POI（可选）。

## Instructions
1. 解析用户给出的起点 / 终点。若只有名称（如「家」「公司」）没有坐标，**先调用 `search_commute_tips_tool`** 拿到候选 lat/lng，挑最匹配的一项。
2. 调用 `compute_optimal_commute_tool`：
   - `origin` / `destinations` 传 `{name?, lat?, lng?, city?, address?}`；有坐标优先用坐标，否则靠 name + city 由服务自动地理编码。
   - `mode`：driving 驾车 / walking 步行 / transit 公交 / cycling 骑行。用户未指定具体方式时设 `compare_modes=true` 横向对比四种方式耗时。
   - 公交 transit **必须**带 `city`（起点城市）。
3. 用工具返回的 JSON 组织回答：**紫色高亮推荐路线**（results 中耗时最短者），给出耗时（分钟）、距离（公里）、换乘数；若存在 `steps_detail` 则输出逐步行程时间线，并可用「当前时间 + 耗时」估算到达时刻。
4. 用户问「附近有什么」时再调用 `search_nearby_commute_pois_tool`。

## Examples
用户：从家到公司怎么走最快
→ `search_commute_tips_tool` 解析「家」「公司」→ `compute_optimal_commute_tool(mode 可 compare_modes)` → 推荐最快方式并给出逐步行程与到达时刻。
