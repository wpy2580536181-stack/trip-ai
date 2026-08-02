# RAG 多源数据增强 & 可信度评分 — 设计文档

> 配套文档：`docs/RAG_OPTIMIZATION.md`（四层优化）· `docs/rag-multi-source-augmentation.md`（路线二 · 多源异构）· `docs/rag-evaluation-plan.md`（评测）· `docs/interview-guide.md`（面试口径）
>
> 适用范围：`trip-backend/`（FastAPI + ChromaDB + bge-small + bge-reranker-base + DeepSeek）

---

## 0. TL;DR（一页结论）

当前 RAG 语料的事实骨架来自**高德 POI**（名称/坐标/品类/地址），但被 embedding、被检索、被喂给 LLM 的**"内容"——景点介绍、标签、评分——是 DeepSeek 自己生成的**。

这带来一个会被面试官一击毙命的问题：

> "既然介绍是 LLM 自己编的，那你 RAG 检索回来喂给 LLM 的，本质上还是这个模型编的内容。这套 RAG 比模型直接答多了什么真实信息？"

**单源 + LLM 自生成 = 语义多样性和信息增量都薄**。这不是数量问题（30,791 条 / 153 城作为作品项目完全够用，不缺量），是**来源血缘**问题。

**本方案**：
1. 引入**独立真实语料**（维基百科 / Wikidata / 官方 POI 详情 / 合规 UGC / 实时 MCP）形成**事实层 + 文本层**多源异构；
2. 为每条文本打 **5 维可信度评分**（authority / freshness / agreement / citation / evidence）作为元信息层；
3. 在**检索融合**与**重排**两个阶段都把可信度作为权重信号，让"权威源"在排序中胜出；
4. RAG 才真正带来模型参数外的真实信息，且每条都可追溯到 `source_url`。

---

## 1. 现状回顾

### 1.1 RAG 引擎

| 模块 | 实现 | 文件 |
|---|---|---|
| Embedding | `BAAI/bge-small-zh-v1.5`（384 维，CPU 单例，查询加 `为这个句子生成表示以用于检索相关文章：` 前缀） | `src/services/rag/embeddings.py` |
| 向量库 | ChromaDB HTTP 客户端，`spots` 集合（hnsw/cosine） | `src/services/rag/chroma_client.py` |
| Query 改写 | 本地关键词 + 停用词；`rewrite_query_with_llm` 是 TODO 降级 | `src/services/rag/query_rewriter.py` |
| 召回 | 三路并行：Chroma 向量 + MySQL FULLTEXT + MySQL rating | `src/services/knowledge_service.py:search_spots` |
| 融合 | RRF（k=60）+ `rrf_merge_with_weights` | `src/services/rag/rrf.py` |
| 重排 | `BAAI/bge-reranker-base`（Cross-Encoder，sigmoid 归一化到 [0,1]） | `src/services/rag/reranker.py` |
| Agent 工具入口 | LangChain tool + POI 缓存 + 韧性（15s 超时 + 1 次重试 + 降级） | `src/services/agent/tools/retrieve_knowledge.py` |

文档拼装（`build_embedding_document`）：

```
{city} {name} {description} {tags} {category}
```

### 1.2 数据生产链路（这是关键）

```
fetch_gaode_poi.py     →  高德 v5/place/text REST   →  data/poi_raw/{city}.json
                          (name, address, coord, category)            [事实骨架]
convert-poi.py         →  DeepSeek LLM 标注          →  data/spots/{city}.json
                          (⚠️ description/tags/rating 是 LLM 生成的)   [内容]
seed_spots.py          →  MySQL 入库
KnowledgeService       →  bge-small-zh-v1.5 嵌入     →  ChromaDB (spots 集合)
                        (create_spot / bulk_import_spots 时双写)
```

**总规模：30,791 条 Spot，覆盖 153 城**（已用 `export_spots_from_db.py` 从线上 DB 反向导出 `data/spots/` 最新快照；此前离线文件仅 767 条/31 城，已归档为历史快照）。

### 1.3 评估现状

`trip-backend/eval/retrieval/`：
- `dataset.py`：15 个标杆景点 × 8 城市 × 3 类别，每个配 3-5 条自然语言 query（共 51 条）。
- `metrics.py`：Hit@K、MRR、按 city/category/query_type 拆分。
- `run.py`：执行入口。

---

## 2. 问题诊断

| # | 痛点 | 影响 | 风险等级 |
|---|---|---|---|
| 1 | **描述层循环依赖**：embedding 内容是 LLM 生成，检索回来又喂给同一个 LLM 家族 | 检索没有真正带来模型参数外的信息 | **致命**（面试会被直接戳穿） |
| 2 | **无数据血缘**：`Spot` 表无 `source_type` / `source_url` / `retrieved_at` / `credibility_score` | 评测时无法区分"事实"和"幻觉" | 高 |
| 3 | **无可信度评分**：仅 `rating` 字段，且本身就是 LLM 标的 | 不可信源和权威源在排序中地位相同 | 高 |
| 4 | **覆盖深度有限**：仅 30 城热门 POI，缺小众景点 / 人文背景 / 季节性 / 票务时效 | 长尾召回率低 | 中 |
| 5 | **口径不一致（已解决）**：经核对线上 DB 实为 **30,791 条 / 153 城**（100% 同步 Chroma 向量），`data/spots/` 离线快照此前仅 767 条/31 城已过期，现已用 `export_spots_from_db.py` 重导并归档；`interview-guide.md` 城市数已校正为 153 | 面试统一按 **30,791 POI / 153 城** 讲，不再脱节 | 已闭环（原致命风险消解） |

---

## 3. 目标与原则

### 3.1 目标

- **G1** 让 RAG 检索回来的内容**确实包含模型参数里没有的真实信息**（百科原文 / 官方票务 / Wikidata 结构化属性）。
- **G2** 每条 Spot 关联的文本都带 **source_type / source_url / credibility_score** 血缘元信息。
- **G3** 在**召回**与**重排**两个阶段都把可信度作为权重信号。
- **G4** 不破坏现有架构，最小改动接入。

### 3.2 原则

- **P1 合规优先**：UGC 严禁全量爬取，优先用 CC BY-SA 授权的开放数据集或官方开放 API。
- **P2 真实增量**：每加一个数据源都要能回答"它比现有内容多了什么？"，而不是再造一层 LLM。
- **P3 降级兼容**：新加的任何一路召回都必须能优雅降级，不影响线上。
- **P4 向量维度一致**：`spot_docs` 与 `spots` 共享 `bge-small-zh-v1.5`（384 维），**不可混模型**。
- **P5 不重写已有**：`Spot` 表结构不动，新增独立 `SpotDoc` 模型 + 独立 Chroma 集合。

---

## 4. 目标架构：事实层 + 文本层

### 4.1 两层模型

```
                          ┌─────────────────────────────────────────┐
                          │              离线 ETL 管道               │
                          │                                           │
  高德 POI REST API ──────▶│  spots（事实层·保持不变）                 │
  （名称/坐标/品类/地址）   │   ├─ fetch_gaode_poi.py                 │
                          │   ├─ convert-poi.py（DeepSeek 冷启动）    │
                          │   └─ seed_spots.py → MySQL + Chroma(spots)│
                          │                                           │
  维基百科/Wikidata ──────▶│  spot_docs（文本层·新增）                │
  官方 POI 详情 ──────────▶│   ├─ fetch_wiki.py / fetch_wikidata.py   │
  合规 UGC 数据集 ────────▶│   ├─ fetch_official.py（高德详情）        │
  实时 MCP 上下文 ────────▶│   ├─ fetch_ugc.py（合规子集）             │
                          │   ├─ 按 heading/段落分块（chunk）         │
                          │   └─ ingest_spot_docs.py                 │
                          │        → MySQL(spot_docs) + Chroma(spot_docs)│
                          └─────────────────────────────────────────┘
                                          │
                                          ▼
                      ┌───────────────────────────────────────┐
                      │       search_spots 多路召回             │
                      │  ① Chroma(spots) 事实向量       w=1.0  │
                      │  ② Chroma(spot_docs) 文本向量   w=0.9  │ ← 新增
                      │  ③ MySQL FULLTEXT(spots)        w=0.7  │
                      │  ④ MySQL 评分排序                w=0.5  │
                      │  ⑤ （可选）实时 MCP 上下文       w=0.8  │ ← 新增
                      │                                       │
                      │  融合 = rrf_merge_with_weights         │
                      │        + credibility_score 调节权重     │
                      │        → Cross-Encoder 重排            │
                      │        → 结果 enrich 来源片段 + 评分    │
                      └───────────────────────────────────────┘
                                          │
                                          ▼
                              retrieve_knowledge_tool
                      （把"真实外部文本"注入 LLM 上下文，
                       每条带 source_type / source_url / credibility）
```

### 4.2 关键设计决策

- **检索仍返回 Spot 级结果**（agent/LLM 要的是标准化景点），但返回的 Spot 上下文**附带命中的真实来源片段**（百科简介 / 官方票务 / Wikidata 属性），让 LLM 拿到模型里没有的信息。
- **文本层独立成集合 `spot_docs`**（而非塞进 `Spot.description`），原因：
  1. 外部文本是长文、需分块；
  2. 来源多样，`source_type` 元信息对重排和治理有价值；
  3. 混合后无法追溯血缘。
- **`rrf.py` 已自带 `rrf_merge_with_weights`** —— 加权融合基础设施现成，无需新造，只需把 `spot_docs` 召回作为新的一路传入并配权重。
- **可信度评分在写入时算好**（`SpotDoc.credibility_score`），避免检索时实时算开销。

---

## 5. 数据源推荐

按"权威性 / 信息增量 / 合规难度"三维度评估，分 5 层。

### 5.1 A. 权威描述层（**必做**，高合规高增量）

| 数据源 | 接入方式 | 权威性 | 增量价值 | 合规风险 | 集成要点 |
|---|---|:---:|---|---|---|
| **中文维基百科** | MediaWiki API `action=query&prop=extracts` | ★★★★★ | 高（中立、引用、模型不熟细节） | 极低（CC BY-SA） | 用 `spot.name + city` 消歧；按二级标题分块 400 字 |
| **英文维基百科** | 同上 | ★★★★★ | 中（国外目的地） | 极低 | 国内景点英文页常更详尽（如长城英文历史） |
| **Wikidata** | SPARQL endpoint | ★★★★★ | 高（结构化属性：坐标、保护级别、UNESCO 标识） | 极低（CC0） | 直接对齐 `spot_id`；可补 P31/P17/P131 等权威标签 |
| **DBpedia** | SPARQL / Lookup | ★★★★ | 中（结构化但偏老） | 极低（CC BY-SA） | 与 Wikidata 互补，覆盖 7+ 语种 |
| **GeoNames** | REST API | ★★★★ | 中（地理/行政区划权威） | 低（CC BY） | 补城市/区域元信息 |
| **OpenStreetMap** | Overpass QL / Nominatim | ★★★★ | 高（POI/边界/公交/无障碍） | 低（ODbL） | 补"周边公交/出入口/无障碍通道" |

### 5.2 B. 官方 / 政府 / 景区直营（**高价值**，时效强）

| 数据源 | 接入方式 | 权威性 | 增量价值 | 合规风险 | 集成要点 |
|---|---|:---:|---|---|---|
| **高德 POI 详情 v5/place/detail** | REST（项目已有 key） | ★★★★ | 高（官方电话/营业时间/票务/URL） | 低 | 补 `open_time` / `tel` / `website` / `ticket` 字段，行字段级合并 |
| **携程/同程 开放平台** | 联盟 API | ★★★★ | 高（票务、点评打分） | 中（需申请） | 适合做"票务实时"和"评论星级" |
| **中国国家文物局 / 省级文物局** | 政府公开数据 | ★★★★★ | 中（文保单位/级别） | 低（公开） | 结构化、可批量入 Spot 元数据 |
| **文化和旅游部 5A/4A 名单** | 公开 PDF/网页 | ★★★★★ | 高（景区等级是强信号） | 极低 | 一次性导入，关联 `spot.rating` 校准 |
| **各景区官方公众号 RSS / sitemap** | RSS/HTML | ★★★★ | 时效（活动/临时关闭） | 低 | 限频 + 标 `last_fetched_at` |

### 5.3 C. UGC / 体验层（**慎做**，高增量高风险）

| 数据源 | 接入方式 | 权威性 | 增量价值 | 合规风险 | 集成要点 |
|---|---|:---:|---|---|---|
| **TripAdvisor Open Data** | 开发者 API | ★★★★ | 高（多语种、星级分布） | 低（官方 API） | 限频 + 标注 locale |
| **Yelp Fusion API / Google Places API** | REST | ★★★★ | 中（国内覆盖弱） | 低 | 补境外目的地 |
| **Foursquare Places API** | REST | ★★★ | 中（POI + 用户签到） | 低 | 补"热门时段" |
| **公开授权的旅行评论数据集** | HuggingFace / Kaggle | ★★★ | 高（一次性、合规） | 极低 | 推荐 `McAuley-Lab/Amazon-Reviews` 旅行子集、Yelp Open Dataset 子集 |
| **Lonely Planet 公开章节** | PDF/HTML | ★★★★ | 中（精校内容） | 中 | 适合做权威背景"长文层" |

### 5.4 D. 学术 / 可信知识库（**加分项**）

| 数据源 | 接入方式 | 权威性 | 增量价值 | 合规风险 | 集成要点 |
|---|---|:---:|---|---|---|
| **维基文库（Wikisource）** | MediaWiki API | ★★★★ | 中（古籍/历史游记原文） | 极低 | 古迹类特别适合（徐霞客游记原文） |
| **百度百科（仅个人作品集）** | HTML 抓取 | ★★★ | 高（中文覆盖比维基广） | **中**（需限频 + robots） | 加 `User-Agent` / 限速 / 标 source |
| **Google Scholar / Semantic Scholar** | REST | ★★★★★ | 低（学术密度高但旅游少） | 低 | 适合"目的地研究"类深度问答 |

### 5.5 E. 实时 / 上下文层（**贯穿**，与 MCP 整合）

| 数据源 | 接入方式 | 权威性 | 增量价值 | 合规风险 | 集成要点 |
|---|---|:---:|---|---|---|
| **高德天气 MCP**（已有） | MCP | ★★★★ | 时效 | 极低 | `research.py` 已调，扩展为 RAG context |
| **高德实时拥堵 / 路况** | MCP | ★★★ | 时效（行程合理性） | 极低 | 适合"出发时间"建议 |
| **节假日 / 调休数据** | 国务院公告 + timor.tech API | ★★★★★ | 高（节假日影响巨大） | 极低 | 一次性导入"该不该去"信号 |

### 5.6 不推荐 ❌

- **大众点评 / 携程 / 美团 直接爬全量**：ToS 与法律风险极高，面试被问"数据合规怎么保证"会翻车。
- **未授权社交媒体抓取**：微博 / 抖音 / 小红书 全量爬取是 ToS 红线。
- **未核验的 LLM 二次生成**：用 LLM-A 生成内容给 LLM-B 喂，本质还是循环依赖。

---

## 6. 可信度评分机制（元信息层）

### 6.1 5 维评分（归一化到 [0,1]）

| 维度 | 含义 | 取值方式 | 权重 |
|---|---|---|:---:|
| `authority` | 来源本身的权威级别 | 1.0=维基/政府/官方 / 0.8=API/合作方 / 0.6=UGC 公开 / 0.4=LLM 生成 | **0.35** |
| `freshness` | 信息新鲜度 | `1 - min(days_since_published, 365) / 365`；≤30 天为 1.0 | 0.20 |
| `cross_source_agreement` | 多源一致度 | N 个独立源都提到同一事实 → `1 - 1/(N+1)` | 0.20 |
| `citation_count` | 引用/反向链接数（百科/学术） | 维基 backlinks / 学术 citations 归一化到 [0,1] | 0.15 |
| `evidence_density` | 证据密度 | 该 Spot 关联的 chunk 数 / 多源覆盖数 | 0.10 |

**综合公式**：

```
credibility_score = 0.35 * authority
                  + 0.20 * freshness
                  + 0.20 * cross_source_agreement
                  + 0.15 * citation_count
                  + 0.10 * evidence_density
```

> 落点：写入时算好，作为 Chroma `metadata` 字段同步存储；查询时直接读取，无需实时计算。

### 6.2 `source_type` 权威性默认值

| `source_type` | `authority` 默认值 | 典型来源 |
|---|:---:|---|
| `wiki` | 1.0 | 中文/英文维基百科、维基文库 |
| `wikidata` | 1.0 | Wikidata SPARQL |
| `official_gov` | 1.0 | 文旅部、国家文物局 |
| `official_scenic` | 0.9 | 景区官方公众号/官网 |
| `gaode_detail` | 0.85 | 高德 POI 详情 |
| `api_partner` | 0.8 | 携程/同程开放平台、TripAdvisor |
| `osm` | 0.85 | OpenStreetMap / Overpass |
| `geonames` | 0.85 | GeoNames |
| `academic` | 0.95 | Google Scholar / Semantic Scholar |
| `ugc_authorized` | 0.6 | 公开授权 UGC 数据集 |
| `ugc_public` | 0.5 | 公开但无授权的 UGC（需谨慎） |
| `llm_generated` | 0.4 | DeepSeek 冷启动标注 |
| `realtime_mcp` | 0.8 | 实时天气/路况 MCP |

### 6.3 `SpotDoc` Schema 扩展

```python
# src/models/spot_doc.py
class SpotDoc(Base, BaseModel):
    __tablename__ = "spot_docs"
    spot_id       = Column(BigInteger, ForeignKey("spots.id"), nullable=False, index=True)
    source_type   = Column(String(20), nullable=False)   # wiki / ugc / official / academic / realtime
    source_name   = Column(String(50))                   # "维基百科" / "高德 POI 详情"
    source_url    = Column(String(512))
    title         = Column(String(200))
    content       = Column(Text, nullable=False)
    chunk_index   = Column(Integer, default=0)
    embedding_id  = Column(String(100), unique=True, nullable=True)
    # 新增可信度元数据
    authority_score     = Column(Float, default=0.5)    # 0~1
    freshness_score     = Column(Float, default=0.5)    # 0~1
    agreement_score     = Column(Float, default=0.0)    # 0~1
    citation_count      = Column(Integer, default=0)
    evidence_density    = Column(Float, default=0.0)    # 0~1
    credibility_score   = Column(Float, default=0.5)    # 综合分（写入时算好）
    published_at        = Column(DateTime)
    retrieved_at        = Column(DateTime, default=now)
    # 全文索引（用于 MySQL 关键词召回）
    __table_args__ = (
        Index("ix_spot_docs_content_ft", "content", mysql_prefix="FULLTEXT"),
    )
```

> 配套：`src/services/rag/chroma_client.py` 新增 `get_spot_docs_collection()`（collection 名 `spot_docs`，`hnsw:space=cosine`）。

### 6.4 在检索融合时落地

```python
# 在 knowledge_service.search_spots 中
def _weight_by_credibility(rrf_score, chunk_meta):
    cred = chunk_meta.get("credibility_score", 0.5)
    return rrf_score * (0.5 + cred)   # 范围 [0.5, 1.5]

# 把 credibility_score 作为 RRF 权重调节
fused = rrf_merge_with_weights(
    paths,
    weights=[1.0, 0.9, 0.7, 0.5],     # 事实/文本/全文/评分
    id_key="id",
    score_adjuster=_weight_by_credibility,
)
```

### 6.5 在 Cross-Encoder 重排时落地

```python
# src/services/rag/reranker.py 增加：
def rerank_with_credibility(query, docs_with_meta, top_k):
    reranked = rerank(query, [d["text"] for d in docs_with_meta], top_k)
    # 用 credibility 作为后置微调
    for r, d in zip(reranked, docs_with_meta):
        r["final_score"] = 0.7 * r["score"] + 0.3 * d.get("credibility_score", 0.5)
    return sorted(reranked, key=lambda x: -x["final_score"])
```

### 6.6 在结果 enrich 时落地

```python
# format_search_results：每条 Spot 后附"来源片段 + 评分标签"
def format_search_results(spots, chunks_by_spot, include_details=True):
    # ... 现有输出 ...
    for spot in spots:
        chunks = chunks_by_spot.get(spot["id"], [])
            if chunks:
                top_chunk = chunks[0]
                lines.append(
                    f"   - 来源片段（{top_chunk['source_name']}, "
                    f"可信度 {top_chunk['credibility_score']:.2f}）："
                    f"{top_chunk['content'][:80]}..."
                )
                lines.append(f"   - 原文链接：{top_chunk['source_url']}")
```

### 6.7 分块（Chunking）策略

新数据进 ChromaDB 之前**几乎都要分块**，但粒度和切分方式因来源而异。`build_embedding_document`（事实层）只对 `description` 等短字段做单块拼接；**文本层**则必须按来源类型分块后再 embedding，否则长文向量被稀释、检索粒度粗、命中差。

#### 6.7.1 为什么要分块

- **Embedding 模型 token 上限**：`bge-small-zh-v1.5` max sequence = 512 token（≈ 700 中文字），超长文本会被截断，丢失尾部信息。
- **长文向量被稀释**：5000 字的维基词条里"门票 60 元"只占 1.2%，整段平均化后该信号的相似度被压到接近 0。
- **检索粒度更细**：用户问"门票多少钱"应该命中票务段，不该返回整篇词条。
- **配合重排**：Cross-Encoder 对短文本打分更准（输入是 query × 短 doc，注意力集中）。

#### 6.7.2 按来源类型选策略

| 来源 | 文本特征 | 推荐分块策略 | 块大小 / 重叠 |
|---|---|---|---|
| **维基百科词条** | 长文（500-5000 字），有 `== 标题 ==` 结构 | **按二级标题**切；无标题则按段落 | 300-400 字 / 50-80 |
| **Wikidata** | 结构化（P31/P17/P131），不是自由文本 | **不切分**，把 properties 序列化为自然语言短句（如"故宫，联合国教科文组织世界文化遗产，1987 年列入"） | 单块 ≤ 200 字 |
| **高德 POI 详情** | 短字段（地址/电话/票务/营业时间） | **不切分**，整段作为一个 chunk | 单块 ≤ 300 字 |
| **官方景区介绍** | 中长文（500-2000 字），有段落 | **按段落**切；段落过长再按句窗口 | 200-400 字 / 50 |
| **UGC 评论 / 游记** | 长文（1000+ 字），口语化、段落碎 | **按段落 + 句窗口滑动**兜底 | 250-400 字 / 60-80 |
| **学术摘要** | 短（200-500 字） | **不切分**，单块 | — |
| **实时 MCP（天气/票务）** | 极短（< 100 字） | **不切分** | — |

#### 6.7.3 推荐默认参数

```python
# 通用默认（适配 bge-small-zh-v1.5 + ChromaDB cosine）
CHUNK_SIZE = 350       # 中文字符
CHUNK_OVERLAP = 60     # 跨块重叠窗口（保证句意连贯）
MIN_CHUNK_SIZE = 80    # 小于这个长度就与相邻块合并，避免碎块
MAX_CHUNK_SIZE = 500   # 超过这个长度强制按句切

# 按来源微调
CHUNK_CONFIG: dict[str, dict] = {
    "wiki":         {"size": 350, "overlap": 60, "split_by": "heading_then_sentence"},
    "wikidata":     {"size": 200, "overlap": 0,  "split_by": "single"},      # 不切
    "gaode_detail": {"size": 300, "overlap": 0,  "split_by": "single"},
    "official":     {"size": 300, "overlap": 50, "split_by": "paragraph"},
    "ugc":          {"size": 300, "overlap": 80, "split_by": "paragraph_then_sentence"},
    "academic":     {"size": 400, "overlap": 0,  "split_by": "single"},
    "realtime_mcp": {"size": 150, "overlap": 0,  "split_by": "single"},
}
```

#### 6.7.4 参考实现

新建 `src/services/rag/chunker.py`，统一封装分块逻辑：

```python
"""统一的分块器，按 source_type 选择策略。"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chunk:
    """分块结果。"""
    text: str
    index: int
    char_start: int
    char_end: int
    metadata: dict = field(default_factory=dict)


_SENTENCE_END = re.compile(r"(?<=[。！？.!?\n])\s*")


def _split_sentences(text: str) -> List[str]:
    """按句号/问号/感叹号/换行切分（后顾正则，不在句中断）。"""
    return [s for s in _SENTENCE_END.split(text) if s.strip()]


def _merge_small(chunks: List[str], min_size: int) -> List[str]:
    """小于 min_size 的块与相邻合并。"""
    merged: List[str] = []
    buf = ""
    for c in chunks:
        if len(c) < min_size:
            buf += c
        else:
            if buf:
                merged.append(buf + c)
                buf = ""
            else:
                merged.append(c)
    if buf:
        merged.append(merged[-1] + buf) if merged else merged.append(buf)
    return merged


def _sliding_window(blocks: List[str], size: int, overlap: int) -> List[str]:
    """句窗口滑动：按 size 切，overlap 字符回退。"""
    text = "".join(blocks)
    if len(text) <= size:
        return [text]
    out: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


def chunk_by_paragraph(text: str, size: int, overlap: int) -> List[Chunk]:
    """按段落切；段落过长按句窗口兜底。"""
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    out: List[Chunk] = []
    for para in paragraphs:
        if len(para) <= size:
            out.append(Chunk(text=para, index=len(out),
                             char_start=0, char_end=len(para)))
        else:
            for s in _sliding_window(_split_sentences(para), size, overlap):
                out.append(Chunk(text=s, index=len(out),
                                 char_start=0, char_end=len(s)))
    return _merge_small_chunks(out, MIN_CHUNK_SIZE=80)


def chunk_by_heading(text: str, size: int, overlap: int) -> List[Chunk]:
    """按维基百科二级标题切（== 标题 ==）；无标题则降级到段落。"""
    parts = re.split(r"={2,}\s*(.+?)\s*={2,}", text)
    # split 会把分隔符捕获到 odd index：parts = [pre, title1, body1, title2, body2, ...]
    if len(parts) <= 1:
        return chunk_by_paragraph(text, size, overlap)
    out: List[Chunk] = []
    intro = parts[0].strip()
    if intro:
        for s in _sliding_window(_split_sentences(intro), size, overlap):
            out.append(Chunk(text=s, index=len(out),
                             char_start=0, char_end=len(s)))
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        section = f"{title}\n{body}" if body else title
        for s in _sliding_window(_split_sentences(section), size, overlap):
            out.append(Chunk(text=s, index=len(out),
                             char_start=0, char_end=len(s)))
    return _merge_small_chunks(out, MIN_CHUNK_SIZE=80)


def chunk_single(text: str, size: int, overlap: int) -> List[Chunk]:
    """不切分，整段作为单块（超 size 则降级到句窗口）。"""
    if len(text) <= size:
        return [Chunk(text=text, index=0, char_start=0, char_end=len(text))]
    return [
        Chunk(text=s, index=i, char_start=0, char_end=len(s))
        for i, s in enumerate(_sliding_window(_split_sentences(text), size, overlap))
    ]


_STRATEGIES = {
    "heading_then_sentence":       chunk_by_heading,
    "paragraph":                   chunk_by_paragraph,
    "paragraph_then_sentence":     chunk_by_paragraph,
    "single":                      chunk_single,
}


def chunk_text(text: str, source_type: str) -> List[Chunk]:
    """统一入口：按 source_type 选策略。"""
    if not text or not text.strip():
        return []
    cfg = CHUNK_CONFIG.get(source_type, CHUNK_CONFIG["official"])
    strategy = _STRATEGIES.get(cfg["split_by"], chunk_by_paragraph)
    chunks = strategy(text, cfg["size"], cfg["overlap"])
    for c in chunks:
        c.metadata = {"source_type": source_type, **cfg}
    return chunks


def _merge_small_chunks(chunks: List[Chunk], min_size: int) -> List[Chunk]:
    """合并过小的块到相邻块。"""
    if not chunks:
        return chunks
    merged: List[Chunk] = []
    for c in chunks:
        if merged and len(c.text) < min_size:
            last = merged[-1]
            last.text = last.text + c.text
            last.char_end = last.char_start + len(last.text)
        elif len(c.text) < min_size and chunks.index(c) < len(chunks) - 1:
            # 与下一块合并（用临时标记）
            c.metadata["_pending_merge"] = True
            merged.append(c)
        else:
            merged.append(c)
    # 第二遍：处理 pending merge
    final: List[Chunk] = []
    for c in merged:
        if c.metadata.pop("_pending_merge", False) and final:
            last = final[-1]
            last.text = c.text + last.text
            last.char_start = 0
            last.char_end = len(last.text)
        else:
            final.append(c)
    # 重新分配 index
    for i, c in enumerate(final):
        c.index = i
    return final
```

#### 6.7.5 几个坑要避

1. **不要在句子中间切断**：用 `(?<=[。！？.!?\n])` 这种"后顾"正则切分，保证每块以句号/问号/感叹号/换行结尾。
2. **重叠不能省**：60-80 字重叠是性价比最高的窗口；少了跨块语义断，多了向量重复浪费存储。
3. **碎块要合并**：维基百科里"另见"/"参考资料"段可能只有 30 字，与其单独成块不如并入上一块。
4. **Metadata 必须完整**：每块至少带 `spot_id` / `source_type` / `source_name` / `source_url` / `chunk_index` / `credibility_score`（写入时算好），检索时按 `spot_id` 聚合回 Spot。
5. **跨语种**：若以后接日文/英文维基，块大小按 **token 数**而非字符数算（`bge-small-zh-v1.5` 对英文支持一般，到时建议换 `bge-m3`）。
6. **Parent-Child 双层索引（可选）**：长文可建"父块（500 字做召回）+ 子块（150 字做精排）"双层结构，召回后取子块更精准。`LangChain` 的 `ParentDocumentRetriever` 就是这个套路，但当前阶段暂不需要，等文本量过万再升级。
7. **冷启动容错**：若一段文本切完只得到 1 块且 < 50 字（极少见，如 Wikidata 单属性），宁可丢弃也不入库，避免噪声向量。
8. **同 chunk 多源**：当同一段事实在 wiki / wikidata / 官方都有，按"同事实 hash 去重"保留 credibility 最高的（避免存储浪费和检索重复投票）。

---

## 7. 实施步骤

### 7.1 Step 1 — Schema 层

- 新建 `src/models/spot_doc.py`（见 §6.3）。
- `src/services/rag/chroma_client.py` 新增 `get_spot_docs_collection()`。
- `src/schemas/knowledge.py` 新增 `SpotDocCreate / SpotDocResponse`。
- 数据库迁移：`create_tables.py` 增加 `spot_docs` DDL。

### 7.2 Step 2 — ETL 脚本

| 脚本 | 作用 | 输入 → 输出 | 分块策略（见 §6.7） |
|---|---|---|---|
| `scripts/fetch_wiki.py` | 按 spots 名称拉中文/英文维基词条 | `data/spots/*.json` → `data/wiki_raw/{city}.json` | `heading_then_sentence`（350/60） |
| `scripts/fetch_wikidata.py` | SPARQL 查 P31/P17/P131 等结构化属性 | Wikidata → `data/wikidata_raw/{city}.json` | `single`（≤200 字） |
| `scripts/fetch_gaode_detail.py` | 调高德 `v5/place/detail` 补票务/营业时间 | 高德 API → `data/gaode_detail/{city}.json` | `single`（≤300 字） |
| `scripts/fetch_ugc.py` | 加载公开授权 UGC 数据集 | 数据集 → `data/ugc_raw/{city}.json` | `paragraph_then_sentence`（300/80） |
| `scripts/ingest_spot_docs.py` | 分块 + 算 credibility + 写 MySQL + embed + 写 Chroma | `data/*_raw` → `spot_docs` 表 + `spot_docs` 集合 | 统一调 `rag.chunker.chunk_text` |
| `scripts/fetch_wiki.py` | 按 spots 名称拉中文/英文维基词条 | `data/spots/*.json` → `data/wiki_raw/{city}.json` |
| `scripts/fetch_wikidata.py` | SPARQL 查 P31/P17/P131 等结构化属性 | Wikidata → `data/wikidata_raw/{city}.json` |
| `scripts/fetch_gaode_detail.py` | 调高德 `v5/place/detail` 补票务/营业时间 | 高德 API → `data/gaode_detail/{city}.json` |
| `scripts/fetch_ugc.py` | 加载公开授权 UGC 数据集 | 数据集 → `data/ugc_raw/{city}.json` |
| `scripts/ingest_spot_docs.py` | 分块 + 算 credibility + 写 MySQL + embed + 写 Chroma | `data/*_raw` → `spot_docs` 表 + `spot_docs` 集合 |

> ⚠️ **注意**：`seed_spots.py` 只写 MySQL、**不**自动 embed Chroma（Chroma 同步仅在 API `create_spot` / `update_spot` 触发）。`ingest_spot_docs.py` 必须显式把分块写入 `spot_docs` 集合，逻辑参照 `KnowledgeService.bulk_import_spots` 的双写模式。

### 7.3 Step 3 — 检索层改造

在 `KnowledgeService.search_spots` 增加**第②路** `Chroma(spot_docs)` 文本向量召回，并把五路用 `rrf_merge_with_weights` + credibility 调节融合：

```python
paths = [path_spots, path_docs, path_mysql_ft, path_mysql_rating, path_mcp]
weights = [1.0, 0.9, 0.7, 0.5, 0.8]
fused = rrf_merge_with_weights(
    paths, weights, id_key="id", score_adjuster=_weight_by_credibility
)
```

- `_spot_docs_search`：查 `spot_docs` 集合 → 命中的 `spot_id` 作为结果（带 `_source="spot_docs"` 与 `source_type`），与原 spots 结果按 `spot_id` 对齐。
- **重排阶段**：把命中 chunk 的真实文本拼进 `_build_spot_document` 的上下文（如 `百科：<片段>`），让 Cross-Encoder 拿到真实证据而非仅有 LLM 生成的描述。

### 7.4 Step 4 — 结果 enrich

`format_search_results` 在每条 Spot 后附加"来源片段"（首个命中 chunk 的 `content` 摘要 + `source_url` + `credibility_score`），使注入 LLM 的上下文包含真实外部文本。

### 7.5 Step 5 — Agent 工具升级

`retrieve_knowledge_tool` 返回结构改为：

```python
{
    "spots": [...],
    "evidence_chunks": [
        {"spot_id": 1, "content": "...", "source_url": "...", "credibility_score": 0.92}
    ]
}
```

让 LLM 收到检索结果时**能引用具体来源**，方便回答"出处"类追问。

---

## 8. 评测方案

### 8.1 评测维度

| 维度 | 指标 | 目标 |
|---|---|---|
| **召回率** | Hit@5 / Hit@10 / MRR（已有） | 多源后 Hit@5 提升 ≥10% |
| **多源覆盖率** | top-5 中 `source_type` 多样性 | 至少 2 种不同 source_type |
| **真实信息增量** | 检索结果中 LLM 自生成内容占比 | 多源后 LLM 占比 ≤30% |
| **Faithfulness** | LLM 回答能否引用 `source_url` 真实来源 | RAGAS Faithfulness ≥ 0.85 |
| **权威源胜出率** | `authority_score ≥ 0.8` 的文本排在 top-3 的比例 | ≥60% |
| **时效性** | 命中 chunk 的 `published_at` 距今天数 | 优先新鲜源 |

### 8.2 评测脚本扩展

- `eval/retrieval/run.py`：增加 `--source-types` 参数，按 source_type 拆分报告。
- `eval/retrieval/metrics.py`：增加 `multi_source_coverage`、`authority_win_rate`、`freshness_score` 三个新指标。
- `eval/retrieval/dataset.py`：增加 `multi-source` 类型的 query（同一查询需同时召回事实层与文本层）。
- `eval/evaluators/ragas.py`：在 Faithfulness 用例里**强制要求引用真实来源片段**（直接回应面试那道致命题）。

---

## 9. 风险与注意事项

| 风险 | 说明 | 缓解 |
|---|---|---|
| **合规红线** | UGC 全量爬取 ToS/法律风险 | 仅用 CC BY-SA 授权数据集 + 官方开放 API；UGC 子集只做"抽样而非全量" |
| **口径一致性（已处理）** | `interview-guide.md` 城市数 343+→153、POI 30,784→30,791；`data/spots/` 已重导对齐 DB（30,791 / 153 城） | 统一口径：**30,791 POI / 153 城（Chroma 全量索引）+ 高德 MCP 实时全库补充** |
| **同名消歧** | 百科/游记对齐 spots 时同名混淆 | 用 `name + city` 双键；查维基词条时校验摘要里是否含 city |
| **Chroma 不同步** | `seed_spots.py` 不触发 embed，`spot_docs` 必须自己写 Chroma | `ingest_spot_docs.py` 显式双写，参考 `bulk_import_spots` 模式 |
| **向量维度一致** | 混用不同 embedding 模型会检索出错 | `spot_docs` 与 `spots` 都用 `bge-small-zh-v1.5`（384 维） |
| **降级兼容** | 新增路径不可用时影响线上 | Chroma(spot_docs) 不可用 → 自动回退到原三路 |
| **跨源重复内容** | 同一事实在 wiki/wikidata/官方都有，浪费存储 | 在 `_spot_docs_search` 后做"按事实 hash 去重"，保留 credibility 最高的 |
| **时间漂移** | 节假日/营业时间/票务会变 | 每次检索时优先召回 `retrieved_at` ≤7 天的 chunk，否则降权 |

---

## 10. 落地路线图

| 阶段 | 内容 | 工作量 | 含金量 | 面试亮点 |
|---|---|---|---|---|
| **P0** ✅ | 扩展 `SpotDoc` schema + credibility 5 列 + `get_spot_docs_collection()` | 0.5d | ★★★★ | "可信度元信息"是高阶考点 |
| **P1A** | **中文维基百科** ETL（fetch + 分块 + 入库 + 第②路召回 + 加权 RRF） | 1d | ★★★★ | 合规、权威、易讲 |
| **P1B** | **Wikidata SPARQL** 补结构化属性（UNESCO/保护级别/坐标） | 0.5d | ★★★★ | "结构化权威属性"是加分项 |
| **P1C** | **高德 POI 详情** 补时效字段（票务/营业时间/电话） | 0.5d | ★★★ | 已有 key，零成本 |
| **P2** | **OpenStreetMap / GeoNames** 补地理元信息 | 1d | ★★★ | 多源结构化 |
| **P3** | **Yelp / TripAdvisor 开放数据**（境外/打分） | 1d | ★★★ | 跨语种/多源一致度 |
| **P4** | 公开 UGC 数据集（合规子集） | 1d | ★★★★ | 真正的多源异构 |
| **P5** | 学术 / Wikisource（长尾/古迹） | 可选 | ★★ | 锦上添花 |

> 时间紧：做完 **P0 + P1（A+B+C）= 2.5 天** 面试就够用；想让项目"硬"：**P0-P4 共 5 天**。
>
> 口径对齐 P0（用户侧）已落地：见 `docs/rag-multi-source-augmentation.md` 跟进记录（`data/spots/` 重导为 30,791 条/153 城 + 各文档口径校正）。本文档 §10 的架构级 P0（`SpotDoc` schema + credibility 5 列 + `get_spot_docs_collection()` + wiki ETL + 加权 RRF + 证据注入）**已于 2026-07-18 实现并通过端到端验证**：插入一条 故宫博物院 维基 `SpotDoc` 后，`search_spots("北京故宫博物院")` 首位返回该景点，`format_search_results` 输出含「来源片段（维基百科，可信度 0.48）+ 原文链接」，pytest 全量 671 passed 无回归。

---

## 11. 面试话术

### 11.1 30 秒版

> 知识库我分了**事实层**和**文本层**。事实层是高德 POI 保证名称/坐标/品类的权威；描述层一开始用 DeepSeek 做冷启动标注——但我很清楚 LLM 生成内容有幻觉风险，所以第二步我**接入了独立真实语料**：
> - 维基百科 + Wikidata 做权威描述与结构化属性；
> - 高德 POI 详情补票务营业时间；
> - 公开授权 UGC 数据集做主观体验。
>
> 检索时事实向量和文本向量**多路并行召回，按可信度加权 RRF 融合**。每条文本入库时都打 **5 维 credibility_score**（authority / freshness / agreement / citation / evidence），Cross-Encoder 重排时作为特征叠加。
>
> 这样 RAG 才真正带来模型参数外的新信息，而不是把模型自己编的内容喂回给自己。每一步来源我都打了 `source_type` 血缘标签，用 RAGAS 的 Faithfulness 验证"回答确实引用了外部真实文本"。

### 11.2 加分心机（主动抛）

- "单一来源是 RAG 的大忌，我做多源异构就是为了解决这个问题。"
- "数据血缘 + 质量治理：每条文本带 `source_type` / `source_url` / `credibility_score`，重排和评测都可追溯。"
- "LLM 标注只是冷启动，真实语料才是终态——这是我有意识的设计取舍，不是偷懒。"
- "合规边界：UGC 用了 CC BY-SA 授权的开放数据集而非全量爬，ToS 安全。"
- "时效治理：`retrieved_at` 距今超过 7 天的 chunk 自动降权，节假日/票务不会用过时信息糊弄用户。"

### 11.3 反面问题应对

| 问题 | 回答 |
|---|---|
| "RAG 比模型直接答多了什么？" | 多源真实语料 + 可信度评分 + 数据血缘，每条都可追溯到 source_url。 |
| "为什么不用更大的 LLM 直接答？" | LLM 没法知道最新票务、节假日调休、景区临时关闭；RAG 把这些时效信息喂进去。 |
| "数据怎么保证合规？" | 仅用 CC BY-SA 授权的开放数据集和官方 API，UGC 抽样而非全量，文档中明确说明边界。 |
| "可信度评分怎么定的？" | 5 维（authority / freshness / agreement / citation / evidence）加权，可调权重，落地在 RRF 融合与 Cross-Encoder 精排两层。 |
| "为什么不爬大众点评？" | ToS 风险，且自生成内容循环依赖本质没解决；改用结构化权威源是更优解。 |

---

## 12. 文件路径索引

### 12.1 现有（保留不动）

- 检索核心：`trip-backend/src/services/knowledge_service.py`（`search_spots` / `build_embedding_document` / `bulk_import_spots`）
- RAG 引擎：`trip-backend/src/services/rag/{chroma_client,embeddings,query_rewriter,reranker,rrf}.py`
- 模型（事实层）：`trip-backend/src/models/spot.py`
- ETL（现有）：`trip-backend/scripts/{fetch_gaode_poi,convert-poi}.py` + `trip-backend/seed_spots.py`
- Agent 工具入口：`trip-backend/src/services/agent/tools/retrieve_knowledge.py`
- 评测：`trip-backend/eval/retrieval/{dataset,metrics,run}.py`

### 12.2 新增（本方案）

- 模型（文本层）：`trip-backend/src/models/spot_doc.py`
- Schemas：`trip-backend/src/schemas/knowledge.py` 增加 `SpotDocCreate / SpotDocResponse`
- Chroma 集合：`trip-backend/src/services/rag/chroma_client.py` 新增 `get_spot_docs_collection()`
- 检索层：`trip-backend/src/services/knowledge_service.py` 新增 `_spot_docs_search` + 加权融合 + enrich
- 重排层：`trip-backend/src/services/rag/reranker.py` 新增 `rerank_with_credibility`
- 可信度工具：`trip-backend/src/services/rag/credibility.py`（5 维评分计算）
- 分块器：`trip-backend/src/services/rag/chunker.py`（按 `source_type` 选策略，详见 §6.7）
- ETL 脚本（新增）：
  - `trip-backend/scripts/fetch_wiki.py`
  - `trip-backend/scripts/fetch_wikidata.py`
  - `trip-backend/scripts/fetch_gaode_detail.py`
  - `trip-backend/scripts/fetch_ugc.py`
  - `trip-backend/scripts/ingest_spot_docs.py`
- 评测扩展：`trip-backend/eval/retrieval/{dataset,metrics,run}.py` 增加多源/可信度指标

### 12.3 配套文档

- `docs/RAG_OPTIMIZATION.md`（检索链路四层优化）
- `docs/rag-multi-source-augmentation.md`（路线二：多源异构 RAG）
- `docs/rag-evaluation-plan.md`（RAG 评测计划）
- `docs/interview-guide.md`（**口径已对齐：30,791 POI / 153 城；离线快照已重导**）
- `docs/rag-data-sources-and-credibility.md`（**本文档**）

---

## 13. 参考实现链接

- `src/services/rag/rrf.py` 中的 `rrf_merge_with_weights`（k=60，多路加权融合基础设施已现成）。
- `src/services/knowledge_service.py:bulk_import_spots`（MySQL + Chroma 双写模式参考）。
- `src/services/agent/resilience.py`（韧性包装，超时 + 重试 + 降级）。
- `src/services/poi_cache.py`（POI 缓存模式参考，用于 `spot_docs` 缓存层）。
- `src/services/rag/chunker.py`（§6.7 的分块器，封装 `chunk_text(text, source_type)` 统一入口）。
