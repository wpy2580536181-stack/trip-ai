# POI ETL 领域知识：降级策略与双写策略

> 本文档是「POI 数据生产 ETL」skill 的领域知识（L3 参考文件）。
> 覆盖 `scripts/fetch_gaode_poi.py` → `scripts/convert-poi.py` → `seed_spots.py` → `scripts/chroma_reindex.py`
> 这条端到端流水线，以及在线 API 写入路径 `src/services/knowledge_service.py` 的两条数据通道。
> 执行该 skill 时，凡涉及「某一步失败怎么办」「数据如何落到 MySQL 与 Chroma」，
> 一律以本文为准，不要凭直觉改写降级/双写顺序。

---

## 一、降级策略（Degradation）

降级发生在三层：抓取层、标注层、重索引层。核心原则：**宁可产出"低质量但可用"的数据，也不要让整条流水线中断。**

### 1.1 抓取层 `scripts/fetch_gaode_poi.py`

| 风险点 | 降级行为 | 代码位置 |
|---|---|---|
| 高德 API 返回非成功（`status != "1"` 或 `infocode != "10000"`） | `search_poi` 直接返回 `[]`，该城市该类别本次结果记为空，**不抛异常、不重试** | L118-119 |
| POI 类型命中排除名单（`EXCLUDE_TYPES`） | 该 POI 被过滤掉，不计入有效结果 | L75-79 |
| 单城市单类别配额上限 | 景点取前 15 条、美食前 10 条、住宿前 5 条有效后截断 | L163 / L173 / L183 |
| 重复 POI | 按 `name|id` 去重（`dedup_pois`） | L123-132 |
| 高德限频 | 城市之间 `await asyncio.sleep(0.3)` | L200 |

> 注意：抓取层**没有**重试机制。API 单条失败 = 该结果缺失，靠"配额上限 + 多城市"整体冗余吸收。

### 1.2 标注层 `scripts/convert-poi.py`

标注层是降级最重的一层（依赖外部 DeepSeek）。

- **JSON 解析三级降级**（`extract_json`，L53）：
  1. 直接 `json.loads`；
  2. 最外层 `{ }` 配对提取 + 正则修尾逗号/尾括号；
  3. 正则提取关键字段；全部失败返回 `None`。
- **LLM 调用重试**：`llm_generate` 单次失败最多重试 **3 次**，间隔 `time.sleep(2)`（L173-184）。
- **标注总降级（兜底）**（`fallback_spot`，L130）：3 次仍失败 → **不再调用 LLM**，生成模板 Spot：
  - `description` = `"{name} 是{city}的{cat_label}，位于{adname}。地址：{address}。"`
  - `rating = 3.5`、`avgCost = 0`、`openTime = "全天"`、`tags = [city]`
  - 输出与正常 LLM 条目**混在同一文件**，下游无法仅凭字段区分来源。
- **限频**：每条标注后 `time.sleep(0.8)`（L190）。

> 关键风险：降级条目与 LLM 条目在 `data/spots/{城市}.json` 中**不可区分**。若需区分，必须在此层给 fallback 条目打标记（当前未做）。

### 1.3 重索引层 `scripts/chroma_reindex.py`

- Chroma 集合不存在：`get_collection` 失败 → `create_collection(name="spots", metadata={"hnsw:space":"cosine"})`（L72-77）。
- 增量索引：默认跳过 Chroma 中已有 `vector_id` 的记录（`WHERE vector_id IS NULL OR vector_id NOT IN <已有 chroma ids>`，L82-105）。
- `--force` 全量重索引，忽略已有记录。

---

## 二、双写策略（Dual-Write）

系统有**两条**数据通道，必须分清，否则会出现"MySQL 有数据但检索不到"或"vector_id 错乱"。

### 2.1 在线路径（API 写入）—— `src/services/knowledge_service.py`

权威源 = **MySQL**；Chroma 是派生向量索引。

- `create_spot`：先生成 `vector_id = uuid4()` 并写入 MySQL 行（L127-141），commit 后再 **best-effort** 写 Chroma（`collection.add`，L165）。
- `update_spot`：更新 MySQL 后，若 `spot.vector_id` 存在则删旧 Chroma 再 `add` 新向量（L220-243）。
- `delete_spot`：先按 `vector_id` 删 Chroma，再删 MySQL（L286-293）。
- **Chroma 不可用守卫**：写入前 `check_chroma_health()`，不可用时跳过 Chroma 写入（L349-357）。即 MySQL 成功、Chroma 失败是被允许的"部分成功"。
- `vector_id` 是 MySQL ↔ Chroma 的**唯一关联键**。

### 2.2 离线批量路径 —— `seed_spots.py` + `chroma_reindex.py`

- `seed_spots.py` **只写 MySQL**，且**不设置 `vector_id`**（保持 NULL，L78 注释明确："ChromaDB 向量同步需通过 API 写入时自动完成 / 如需为已有数据同步向量，请通过管理端 API 或重索引触发"）。
- `chroma_reindex.py` 读 MySQL → `embed_documents` 生成向量 → 写 Chroma：
  - `vector_id` 取值：已有则沿用，否则 `f"spot-{spot_id}"`（L133）。
  - 增量跳过已有 `vector_id`；`--force` 全量。

> ⚠️ **一致性断层（务必记住）**：
> 在线路径的 `vector_id` 是 `uuid4()`，离线路径是 `spot-{id}`。**两者约定不同、互不互通**。
> 同一 `spots` 集合里混用两种 id 不会冲突（id 字符串不同），但意味着：seed 进来的数据若后续走 API 更新，
> `update_spot` 会因 `spot.vector_id` 已是 `spot-{id}` 而按该 id 操作——行为自洽，但**绝不要手动把 seed 的 `vector_id` 改成 uuid**。
> 修复离线数据后，**必须**再跑一次 `chroma_reindex.py` 才能被 RAG 检索到。

### 2.3 一致性保证与操作清单

1. **MySQL 永远是 single source of truth**；Chroma 可随时从 MySQL 重建（reindex）。
2. 新灌数据走 `seed_spots.py` 后，**紧接着跑 `chroma_reindex.py`（非 --force）**，否则新数据只在 MySQL、RAG 检索不到。
3. 在线 API 产生的"MySQL 成功 / Chroma 失败"脏数据，用 `chroma_reindex.py --force` 重建即可。
4. 文档文本（`_build_document`）格式必须与 `knowledge_service` 的 embedding 文档一致：
   `"{city} {name} {description} {tags} {category}"`，否则向量分布漂移（见 `seed_spots.py` L22-25 与 `chroma_reindex.py` L32-35）。

---

## 三、一句话速查

- 抓取失败 = 该结果缺失（无重试）；标注失败 = 模板兜底（rating 3.5）；重索引失败 = 建新集合。
- 双写有两条路：**API 路径** MySQL+Chroma 同步、`vector_id=uuid4`；**seed 路径** 先 MySQL 后 reindex、`vector_id=spot-{id}`。
- 不论哪条路，**seed/reindex 之后不跑 reindex = 检索不到**；**Chroma 脏了用 `--force` 重建**。
