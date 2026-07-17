---
name: 酒店搜索
description: 按城市与条件检索推荐酒店
tags: [hotel, 酒店, search, 住宿]
kind: tool
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
