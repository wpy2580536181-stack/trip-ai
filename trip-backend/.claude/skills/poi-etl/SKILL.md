---
name: POI ETL
description: "管理 POI 数据采集、LLM 标注、MySQL/Chroma 双写入库的端到端流水线。当用户提到 'POI 抓取'、'数据导入'、'景点导入'、'高德数据'、'reindex'、'Chroma 重索引'、'seed 数据'、'知识数据生产'、'数据管道'、'ETL'、'双写'、'降级策略'时触发。也用于排查 '检索不到数据'、'MySQL 有但 Chroma 没有'、'导入失败'等数据一致性问题。"
---

# POI ETL — 数据生产流水线

## 概述

本 Skill 覆盖从高德 API 抓取 → DeepSeek LLM 标注 → MySQL + Chroma 双写入库的完整流水线。
执行时涉及的所有降级、双写、一致性操作，一律以 `references/degradation-dual-write.md` 为准。

## 流水线步骤

1. **抓取**：`scripts/fetch_gaode_poi.py` — 按城市 × 类别（景点/美食/酒店）调用高德 API
2. **转换**：`scripts/convert-poi.py` — 调用 DeepSeek 生成 description/tags/rating
3. **导入**：`prisma/seed-knowledge.ts` / `src/services/knowledgeService.ts` — 写入 MySQL + Chroma
4. **重索引**：`scripts/re-embed-spreads.ts` — 已有数据的向量重建

## 关键规则

- **MySQL 是权威源**；Chroma 可随时从 MySQL 重建
- 在线路径 `vector_id = uuid4()`，离线路径 `vector_id = spot-{id}`，两者约定不同
- seed/reindex 之后不跑 reindex = 检索不到
- Chroma 脏了用 `--force` 重建

详见 `references/degradation-dual-write.md`。
