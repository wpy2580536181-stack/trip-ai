---
name: 路线优化
description: 基于通勤择优服务，给出多出行方式下的最优路线
tags: [route, 路线, commute, 通勤, 优化]
kind: agent
---

# 路线优化 Skill

## Trigger
用户意图包含「路线 / 通勤 / 怎么去 / 怎么走 / 最优路线 / 最快」并给出起终点时触发。

## Instructions
调用底层 `commute_service` / `optimize_service` 计算多出行方式（驾车/公交/步行/骑行）
路线，用紫色高亮推荐路线，输出逐步行程时间线与到达时刻。

## Input Schema
```json
{"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "mode": {"type": "string"}}, "required": ["origin", "destination"]}
```

## Examples
用户：从家到公司怎么走最快
→ 计算驾车/公交/步行/骑行并推荐最快路线。
