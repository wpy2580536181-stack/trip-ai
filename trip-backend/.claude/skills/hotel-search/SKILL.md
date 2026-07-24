---
name: hotel-search
description: "按城市检索推荐酒店。当用户询问'住哪''住宿推荐''酒店''宾馆''民宿'或需要提供某城市的住宿建议时触发。支持预算/星级筛选，返回酒店名称与简介。"
---

# 酒店搜索 Skill

## Trigger
用户意图包含「酒店 / 住宿 / 住哪」且提供了城市时触发。

## Instructions
调用 `search_hotels` 工具，按城市与（可选）预算/星级检索酒店，返回名称与简介。

## Input Schema
```json
{"type": "object", "properties": {"city": {"type": "string"}, "budget": {"type": "string"}}, "required": ["city"]}
```

## Examples
用户：成都住哪好
→ 调用 search_hotels(city="成都")
