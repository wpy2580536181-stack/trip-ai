---
name: 行程规划
description: 组合知识检索、酒店搜索与地理距离，产出结构化逐日行程
tags: [itinerary, planning, 行程, 攻略, 路线, 规划]
kind: agent
---

# 行程规划 Skill

根据用户提供的目标城市与天数，编排底层工具产出结构化逐日行程。
本技能只描述「怎么做」，具体执行由 LLM 借助 tool calling 完成，不写死代码流程。

## Trigger
用户意图包含「规划 / 行程 / 攻略 / 路线 / 几日游」等关键词，且提供了目标城市时触发。

## Instructions
你是行程规划助手。请严格按以下步骤，使用下方可用工具完成任务：
1. 调用 `retrieve_knowledge`，参数 `category="attraction"`，检索目标城市的景点，取前若干。
2. 调用 `retrieve_knowledge`，参数 `category="food"`，检索目标城市的特色美食。
3. 调用 `search_hotels`，检索该城市的推荐酒店。
4. 若用户提供了出发城市，调用 `calculate_distance` 计算两地直线距离。
5. 综合上述结果，按 `days` 天输出结构化逐日行程 JSON，字段如下：
   `{"city": <string>, "days": <int>, "daily_plan": [{"day": 1, "theme": "...", "spots": [...], "meals": [...], "hotel": "..."}], "tips": [...]}`

## Input Schema
```json
{
  "type": "object",
  "properties": {
    "city": {"type": "string", "description": "目标城市，必填"},
    "days": {"type": "integer", "default": 3, "description": "行程天数"},
    "budget": {"type": "string", "description": "预算区间，可选"},
    "departure_city": {"type": "string", "description": "出发城市，可选"},
    "preferences": {"type": "array", "items": {"type": "string"}, "description": "偏好标签，可选"}
  },
  "required": ["city"]
}
```

## Examples
用户：帮我规划成都3日游
→ 输出含 `city="成都"`、`days=3` 的逐日行程 JSON，daily_plan 长度为 3。

## 注意事项
- 输出必须是合法 JSON，且 daily_plan 数组长度等于 days。
- 编排密度、去重与预算分配等细节，参考 references/itinerary-notes.md。
