# RAG 多数据源增强方案（路线二）

> 目标：把当前"高德 POI（事实）+ DeepSeek 标注（描述）"的**单源语料**，升级为**多源异构 RAG**，让检索真正带来模型参数里没有的真实信息增量。
> 配套：`docs/interview-guide.md`、`docs/RAG_OPTIMIZATION.md`、`docs/rag-evaluation-plan.md`
> 适用代码：`trip-backend/`（FastAPI + ChromaDB + bge-small + bge-reranker）

---

## 0. 为什么必须做这件事（一页结论）

当前 RAG 语料的事实骨架来自高德 POI（名称/坐标/品类/地址），但被 embedding、被检索、被喂给 LLM 的**"内容"——景点介绍、标签、评分——是 DeepSeek 生成的**。

这带来一个会被犀利面试官一击毙命的问题：

> "既然介绍是 LLM 自己编的，那你 RAG 检索回来喂给 LLM 的，本质上还是这个模型编的内容。这套 RAG 比模型直接答多了什么真实信息？"

**单一来源 + 内容自生成 = 语义多样性和信息增量都薄。** 这是核心弱点，不是数量（DB 现 30,791 条 / 153 城，作为作品项目完全够用，不缺量）。

解决方向：引入**独立的、真实存在的文本语料**（权威描述 + 主观体验 + 时效信息），与高德事实层形成多源异构，并在检索层做**按来源可靠度的加权融合**。

> ⚠️ **口径一致性（已修正）**：经核对线上 DB（`spots` 表共 30,791 条 / 153 城，且 100% 已同步 `vector_id` 进 Chroma），`docs/interview-guide.md` 的"30,784 POI / 343+ 城市"中**城市数偏大**（实际 153）。`data/spots/` 离线快照此前仅 767 条 / 31 城、已与线上脱节，现已用 `export_spots_from_db.py` 从 DB 反向导出最新快照（30,791 条 / 153 城）并归档旧文件。面试统一口径：**"离线精标语料 30,791 POI / 153 城（Chroma 全量索引）+ 运行时高德 MCP 实时全量 POI 补充"**。本方案要补的是**来源结构**（单源 → 多源异构），而非数量。

---

## 1. 目标架构：事实层 + 文本层

保留现有"一个 Spot 一条向量"的事实层不变，新增独立的**文本层**（分块后的真实外部文本），二者通过 `spot_id` 关联。

```
                          ┌─────────────────────────────────────────┐
                          │              离线 ETL 管道               │
                          │                                           │
  高德 POI REST API ──────▶│  spots（事实层）                         │
  （名称/坐标/品类/地址）   │   ├─ fetch_gaode_poi.py                 │
                          │   ├─ convert-poi.py（DeepSeek 标注）      │
                          │   └─ seed_spots.py → MySQL + Chroma(spots)│
                          │                                           │
  维基/百度百科 API ──────▶│  spot_docs（文本层·新增）                │
  公开游记/点评数据集 ────▶│   ├─ fetch_wiki.py / fetch_ugc.py         │
  官方景区介绍 ───────────▶│   ├─ 按 heading/段落分块（chunk）         │
                          │   └─ ingest_spot_docs.py                 │
                          │        → MySQL(spot_docs) + Chroma(spot_docs)│
                          └─────────────────────────────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────┐
                      │       search_spots 多路召回         │
                      │  ① Chroma(spots)  事实向量   w=1.0  │
                      │  ② Chroma(spot_docs) 文本向量 w=0.9  │ ← 新增
                      │  ③ MySQL FULLTEXT(spots)   w=0.7    │
                      │  ④ MySQL 评分排序           w=0.5    │
                      │  加权 RRF 融合 → Cross-Encoder 重排  │
                      │  结果仍 spot 级，但 enrich 来源片段  │
                      └───────────────────────────────────┘
                                          │
                                          ▼
                              retrieve_knowledge_tool
                      （把"真实外部文本"注入 LLM 上下文）
```

**关键设计决策：**
- **检索仍返回 Spot 级结果**（agent/LLM 要的是标准化景点），但返回的 Spot 上下文里**附带命中的真实来源片段**（百科简介 / 游记高亮句），让 LLM 拿到模型里没有的信息。
- **文本层独立成集合 `spot_docs`**（而非塞进 `Spot.description`），原因：外部文本是长文、需分块、来源多样、`source_type` 元信息对重排和治理有价值；混合后无法追溯血缘。
- **`rrf.py` 已自带 `rrf_merge_with_weights`** —— 加权融合基础设施现成，无需新造，只需把 `spot_docs` 召回作为新的一路传入并配权重。

---

## 2. 数据源分级建议

按"费力程度 / 信息增量 / 合规风险"三维度排序。

| 级别 | 数据源 | 补的是哪一层 | 增量价值 | 合规/难度 | 建议 |
|---|---|---|---|---|---|
| **A（必做）** | **维基百科 / 百度百科 景点词条** | 权威描述层 | 高（权威、长文本、模型未必记得细节） | 低（维基有开放 API；百度百科需爬虫限频） | ✅ 首推，半天可成 |
| **B（高价值）** | **公开游记 / 点评数据集** | 主观体验 + 时效层 | 最高（UGC 是 RAG 最大增量来源） | 中（注意 ToS；用开放授权数据集或明确标注的样本） | ✅ 强烈建议 |
| **C（可选）** | **官方景区介绍 / 高德 POI 详情** | 权威 + 时效层 | 中 | 低-中 | 时间够再做 |
| 不推荐 | 大众点评/携程 直接爬全量 | — | — | **高（ToS/法律风险）** | ❌ 不合规，别碰 |

### A. 维基百科 / 百度百科（权威描述层）
- **维基百科（首选，合规）**：`https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&titles=<景点名>&format=json&explaintext=1`。用景点名 + 城市做对齐（同名消歧：取摘要里包含城市名的条目）。
- **百度百科（覆盖更好，需爬虫）**：无官方 API，按 `https://baike.baidu.com/item/<词条>` 抓取，必须加 `robots.txt` 遵守 + 限频（≥1s/请求）+ 仅用于个人作品集、不商用。
- 输出：`data/wiki_raw/{city}.json`，按 `spot.name` 建索引。

### B. 公开游记 / 点评（主观体验 + 时效层）
- **合规优先**：选明确开放授权的数据集（如学术论文配套数据集、Kaggle 上 CC 授权的旅行评论集），或**手工精选少量真实游记片段并标注来源 URL**（作品集足够，且面试可如实说明"抽样而非全量爬取"）。
- **不要直接爬大众点评/携程全量**：ToS 与法律风险高，且面试被问"数据合规怎么保证"会翻车。如实讲"用了公开授权/抽样的 UGC"反而加分。
- 输出：`data/ugc_raw/{city}.json`，字段含 `spot_name`、`text`、`source`、`source_url`。

### C. 官方 / 实时（时效层）
- 高德 POI 详情接口可补 `open_time`/`tel` 等；景区官网抓取覆盖低，作为锦上添花。

---

## 3. 实施步骤（落到具体文件）

### 3.1 Schema 新增文本层

`src/models/spot_doc.py`（新模型，对应新表 `spot_docs`）：

```python
class SpotDoc(Base, BaseModel):
    __tablename__ = "spot_docs"
    spot_id     = Column(BigInteger, ForeignKey("spots.id"), nullable=False, index=True)
    source_type = Column(String(20), nullable=False)   # wiki / ugc / official
    source_name = Column(String(50))                    # "维基百科" / "公开游记集"
    source_url  = Column(String(512))
    title       = Column(String(200))
    content     = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    embedding_id = Column(String(100), unique=True, nullable=True)
    # FULLTEXT(content) for MySQL keyword path over text layer
```

`src/services/rag/chroma_client.py`：在 `get_*_collection` 之外新增 `get_spot_docs_collection()`（collection 名 `spot_docs`，`hnsw:space=cosine`）。

### 3.2 分块（Chunking）策略

外部文本是长文，必须分块再 embedding，否则长文向量被稀释、命中差。

- **百科**：按 `== 二级标题 ==` 切分；无标题则按句子滑动窗口（窗口 400 字、重叠 60 字）。
- **游记**：按段落切分，单段过长再按句窗口切。
- 每块元数据：`{ source_type, spot_id, city, spot_name, source_url, chunk_index }`。

### 3.3 ETL 脚本（新增）

| 脚本 | 作用 | 输入 → 输出 |
|---|---|---|
| `scripts/fetch_wiki.py` | 按 spots 名称拉百科词条 | `data/spots/*.json` → `data/wiki_raw/{city}.json` |
| `scripts/fetch_ugc.py` | 加载/对齐公开 UGC | 数据集 → `data/ugc_raw/{city}.json` |
| `scripts/ingest_spot_docs.py` | 分块 + 写 MySQL + embed + 写 Chroma | `data/*_raw` → `spot_docs` 表 + `spot_docs` 集合 |

> 注意：`seed_spots.py` **只写 MySQL、不自动 embed Chroma**（Chroma 同步仅在 API `create_spot`/`update_spot` 触发）。`ingest_spot_docs.py` 必须显式把分块写入 `spot_docs` 集合，逻辑参照 `KnowledgeService.bulk_import_spots` 的双写模式。

### 3.4 检索层改造（核心）

在 `KnowledgeService.search_spots` 增加**第 ② 路：Chroma(spot_docs) 文本向量召回**，并把四路用 `rrf_merge_with_weights` 融合：

```python
# 新增：文本层向量召回（返回命中 chunk 映射回 spot_id）
task_docs = asyncio.create_task(
    KnowledgeService._spot_docs_search(rewritten_query, city, category, limit * 2)
)
# ...
# 融合（权重：事实向量 1.0 / 文本向量 0.9 / mysql全文 0.7 / 评分 0.5）
paths = [path_spots, path_docs, path_mysql_ft, path_mysql_rating]
weights = [1.0, 0.9, 0.7, 0.5]
fused = rrf_merge_with_weights(paths, weights, id_key="id")
```

- `_spot_docs_search`：查 `spot_docs` 集合 → 命中的 `spot_id` 作为结果（带 `_source="spot_docs"`、命中的 `source_type`），与原 spots 结果按 `spot_id` 对齐。
- **重排阶段**：把命中 chunk 的真实文本拼进 `_build_spot_document` 的上下文（如 `百科：<片段>`），让 Cross-Encoder 拿到真实证据而非仅有 LLM 生成的描述。
- **结果 enrich**：`format_search_results` 在每条 Spot 后附加"来源片段"（首个命中 chunk 的 `content` 摘要 + `source_url`），使注入 LLM 的上下文包含真实外部文本。

### 3.5 评测扩展

- `eval/retrieval/`：新增**多源覆盖率**指标（检索结果中来自 wiki/ugc 的比例）、按 `source_type` 拆分的 Hit@K。
- `eval/evaluators/ragas.py`：在 Faithfulness 用例里**强制要求引用真实来源片段**，验证 RAG 确实带来模型外信息（直接回应面试那道致命题）。
- 新增 fixture 维度：`multi-source`（同一查询需同时召回事实层与文本层）。

---

## 4. 分阶段路线图（按投入选）

| 阶段 | 内容 | 工作量 | 面试含金量 |
|---|---|---|---|
| **P0 对齐口径（已完成）** | 重导 `data/spots/` 离线快照至 30,791 条 / 153 城（归档旧 31 文件）；`interview-guide.md` 城市数 343+→153 | 0.5h | 避免翻车（最高优先） |
| **P1 百科权威层（A）** ✅ | `fetch_wiki.py` + `ingest_spot_docs.py` 分块入库 + 第②路 `spot_docs` 召回 + 加权 RRF + `rerank_with_credibility` + 证据注入 `format_search_results`；2026-07-18 **真实语料灌库完成**（153 城跑完→275 条维基→写入 `spot_docs` 288 块/270 景点，95 城命中、58 城零命中；西湖等已覆盖；降级重排下证据归因正确） | 0.5–1 天 | ★★★ 合规、易讲、增量明显 |
| **P2 UGC 体验层（B）** | 公开/抽样 UGC 对齐 + 入库 + 评测维度 | 1–2 天 | ★★★★ 最大增量，最显"多源异构" |
| **P3 治理与评测闭环** | 数据血缘标注、`source_type` 权重可配、ragas 引用验证 | 0.5–1 天 | ★★★★ 命中高阶考点（data lineage/quality） |
| **P4 官方/实时（C）** | 高德详情补时效字段 | 可选 | ★★ 锦上添花 |

> 时间紧：做完 **P0 + P1** 面试就够用；想让项目"硬"：**P0–P3**。

---

## 5. 面试话术：把弱点讲成亮点

**30 秒版：**
> 知识库我分了**事实层**和**文本层**。事实层是高德 POI 保证名称/坐标/品类的权威，描述层一开始用 LLM 做冷启动标注——但我很清楚 LLM 生成内容有幻觉风险，所以第二步我**接入了独立真实语料**：维基/百度百科做权威描述、公开 UGC 做主观体验和时效。检索时事实向量和文本向量**两路并行召回，按来源可靠度加权 RRF 融合**，Cross-Encoder 重排时把真实来源片段喂进去。这样 RAG 才真正带来模型参数外的新信息，而不是把模型自己编的内容喂回给自己。每一步来源我都打了 `source_type` 血缘标签，用 ragas 的 Faithfulness 验证"回答确实引用了外部真实文本"。

**加分心机（主动抛）：**
- "单一来源是 RAG 的大忌，我做多源异构就是为了解决这个问题。"
- "数据血缘 + 质量治理：每条文本带 source_type/source_url，重排和评测都可追溯。"
- "LLM 标注只是冷启动，真实语料才是终态——这是我有意识的设计取舍，不是偷懒。"

---

## 6. 风险与注意事项

1. **口径一致性（已处理）**：`interview-guide.md` 城市数 343+ 已改为真实 153；`data/spots/` 已重导对齐 DB（30,791 / 153 城）。面试统一口径：30,791 POI / 153 城。
2. **合规红线**：UGC 只用开放授权或明确标注的样本，禁止爬取大众点评/携程全量。
3. **同名消歧**：百科/游记对齐 spots 时用"名称 + 城市"双键，避免把别的城市的同名景点错配。
4. **Chroma 不同步**：`seed_spots.py` 不触发 embed，`spot_docs` 必须自己写 Chroma，别漏。
5. **向量维度一致**：`spot_docs` 集合与 `spots` 都用同一 `bge-small-zh-v1.5`（384 维），不可混模型。
6. **降级兼容**：Chroma(spot_docs) 不可用时，检索应自动回退到原有三路，不影响线上。

---

## 7. 配套文档与代码索引

- 现有：`docs/interview-guide.md`、`docs/RAG_OPTIMIZATION.md`、`docs/rag-evaluation-plan.md`
- 检索核心：`src/services/knowledge_service.py`（`search_spots` / `build_embedding_document` / `bulk_import_spots`）
- 融合：`src/services/rag/rrf.py`（`rrf_merge_with_weights` 已存在）
- 重排：`src/services/rag/reranker.py`（`bge-reranker-base`）
- 向量：`src/services/rag/chroma_client.py`、`src/services/rag/embeddings.py`
- 模型：`src/models/spot.py`（事实层）、新增 `src/models/spot_doc.py`（文本层）
- ETL：`scripts/fetch_gaode_poi.py`、`scripts/convert-poi.py`、`scripts/seed_spots.py`（现有）；新增 `scripts/fetch_wiki.py` / `fetch_ugc.py` / `ingest_spot_docs.py`
- Agent 工具：`src/services/agent/tools/retrieve_knowledge.py`
