# 旅游开放数据源调研清单

> 目的：为 Trip 项目的 RAG 知识库引入多源异构真实语料，摆脱"高德 POI 单源 + DeepSeek 自生成描述"的循环依赖。
> 配套：`docs/rag-multi-source-augmentation.md`（路线二方案）、`docs/RAG_OPTIMIZATION.md`
> 调研日期：2026-07-16
> 适用代码：`trip-backend/`（FastAPI + ChromaDB + bge-small + bge-reranker）

---

## 0. 一页结论

| 维度 | 推荐组合 |
|---|---|
| **景点权威描述层（A）** | Wikidata SPARQL + 维基百科 API + 文旅部 5A 名录 |
| **景点事实层补充** | Overture Maps Places（70M+ POI，CDLA Permissive v2.0） + Foursquare OS Places（100M+ POI，Apache 2.0） |
| **酒店信息** | OSM Overpass（tourism=hotel + stars/rooms 标签）+ Overture Places + 杭州文旅数据在线（仅杭州，政府权威） |
| **餐厅信息** | Yelp Open Dataset（学术经典）+ OpenTable 多准则数据集 + OSM Overpass（amenity=restaurant + cuisine） |
| **统一 ID 桥接** | Overture GERS（Global Entity Reference System）—— 跨源 join 的稳定 ID |
| **不推荐** | 大众点评/携程全量爬取（ToS/法律风险高）、Agoda/Booking 商业 API 直连（ToS 风险） |

**对 Trip 项目的具体建议**：当前 30,791 条/153 城的语料（事实层已较完整），核心短板是**单一来源 + 描述层 LLM 自生成**，而非数量；因此先做 **P1（Wikidata+维基百科权威层）** 补真实信息增量，再用 **Overture Places 按城市 bbox 批量补 POI 事实层**，餐厅补 Yelp 公开数据集即可覆盖北美样板，国内餐厅用 OSM amenity=restaurant 兜底。

---

## 1. 景点（Tourist Attractions）

### 1.1 Wikidata（SPARQL 端点） ⭐ 首推

| 维度 | 详情 |
|---|---|
| **数据规模** | 全球 ~2.6 亿实体，其中 `wd:Q570116` (Tourist Attraction) 子树覆盖数十万景点；中国 5A/4A 景区基本有词条 |
| **更新频率** | 实时（社区持续编辑）；SPARQL 端点通常分钟级反映变更 |
| **覆盖地区** | 全球，中文/英文双语 label |
| **获取方式** | SPARQL 端点 `https://query.wikidata.org/sparql`，无需 API Key；支持 JSON/XML/CSV/TSV 输出 |
| **权威性** | 高（维基媒体基金会维护，结构化数据源自维基百科 infobox） |
| **成本** | 完全免费，CC0 协议 |
| **核心字段** | `rdfs:label`（名称）、`wdt:P625`（坐标）、`wdt:P131`（所在行政区）、`wdt:P18`（图片）、`wdt:P856`（官网）、`wdt:P571`（建立时间）、`schema:description`（描述） |
| **样例 SPARQL** | 见下方代码块 |
| **限制** | Fair Use Policy：单 IP 100 请求/秒、并发 50、结果集 ≤10000 行、查询超时 120s；大查询建议用 `LIMIT`/分页或下载 dump |
| **适合场景** | Trip 项目"文本层权威描述"主源，配合 Wikipedia API 取长文摘要 |

```sparql
# 查询中国所有 5A 级旅游景点
SELECT ?item ?itemLabel ?itemDescription ?coord ?image WHERE {
  ?item wdt:P31/wdt:P279* wd:Q570116.       # instance of tourist attraction
  ?item wdt:P17 wd:Q148.                      # country = China
  OPTIONAL { ?item wdt:P625 ?coord. }
  OPTIONAL { ?item wdt:P18 ?image. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en". }
}
LIMIT 5000
```

### 1.2 Wikipedia API（开放接口）

| 维度 | 详情 |
|---|---|
| **数据规模** | 中文维基 130 万+ 条目，英文 680 万+ |
| **更新频率** | 实时 |
| **覆盖地区** | 全球，多语言 |
| **获取方式** | `https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&titles=<景点名>&format=json&explaintext=1` |
| **权威性** | 高（社区审核 + 来源引用） |
| **成本** | 免费，CC BY-SA 3.0 |
| **核心字段** | `extract`（纯文本摘要）、`pageimage`、`coordinates`、`categories` |
| **限制** | 单次 `extracts` 长度 ≤500 字符（除非 `exintro=0`）；建议配合 `prop=extracts|coordinates|categories` 多 prop 拉取 |
| **适合场景** | Trip 项目 `fetch_wiki.py` 的主数据源；与 Wikidata 通过 `wikidataId` 互查 |

### 1.3 文化和旅游部数据服务栏目（政府权威） ⭐ 中国景点最权威

| 维度 | 详情 |
|---|---|
| **入口** | https://sjfw.mct.gov.cn/ |
| **数据集** | ① 国家 5A 级旅游景区（337 个，截至 2025-03-11）<br>② 五星级旅游饭店<br>③ 国家级滑雪旅游度假地<br>④ 国家级旅游休闲街区<br>⑤ 国家工业旅游示范基地 |
| **数据规模** | 5A 景区 ~337 个（按省列出名称+评定年份），五星饭店按季度统计报告 |
| **更新频率** | 不定期（5A 景区约每年新增 10-20 家，季度统计报告） |
| **覆盖地区** | 中国大陆 31 省市 + 兵团 |
| **获取方式** | 网页列表，无 API；需爬虫或手工整理（页面静态，限频 1s/请求即可） |
| **权威性** | **最高**（国务院文旅部官方发布） |
| **成本** | 免费 |
| **核心字段** | 景区名称、评定年份、所在省市（无坐标，需另行地理编码） |
| **适合场景** | Trip 项目中国景点的"白名单"，作为权威性背书；坐标可用高德 inputtips 接口补全 |

### 1.4 长三角 5A 景区数据集（学术化整理）

| 维度 | 详情 |
|---|---|
| **入口** | https://www.geodata.cn/main/face_science_detail?guid=129215637810316 |
| **数据规模** | 长三角 5A 景区表格 + 空间点位 |
| **字段** | 景区名称、评定年份、所在省市、百度经纬度、WGS84 经纬度 |
| **覆盖地区** | 长江三角洲（上海/江苏/浙江/安徽） |
| **获取方式** | 在线订单申请（需注册，免费） |
| **权威性** | 高（国家地球系统科学数据中心，源自文旅部 + 百度 API 地理编码） |
| **适合场景** | 长三角样板验证；可作为 RAG 评测集的"金标准" |

### 1.5 Overture Maps Places（全球 POI 巨库） ⭐ 大规模事实层

| 维度 | 详情 |
|---|---|
| **入口** | https://overturemaps.org/download/ |
| **数据规模** | 70M+ POI（全球，2026 数据） |
| **更新频率** | 月度发布（每月 17 日左右） |
| **覆盖地区** | 全球 |
| **获取方式** | ① S3 直读：`s3://overturemaps-us-west-2/release/2026-06-17.0/theme=places/type=place/*`<br>② Azure Blob：`https://overturemapswestus2.blob.core.windows.net/release/...`<br>③ Python CLI：`pip install overturemaps && overturemaps download --bbox=<lon_min,lat_min,lon_max,lat_max> -f geojson --type=place -o out.geojson`<br>④ DuckDB：`LOAD spatial; LOAD httpfs; COPY(SELECT ... FROM read_parquet('s3://...') WHERE bbox.xmin BETWEEN ...) TO 'out.geojson'` |
| **权威性** | 高（AWS/Meta/Microsoft/TomTom 等联合发起，Tripadvisor/Uber/Meta 已采用） |
| **成本** | 免费，CDLA Permissive v2.0（注：源自 OSM 的部分带 ODbL 要求，需 attribution） |
| **核心字段** | `id`（GERS 稳定 ID）、`names.primary`、`categories.primary`、`categories.basic_category`、`confidence`（0-1 存在置信度）、`websites`、`phones`、`addresses`、`geometry` |
| **景点相关 category** | `tourist_attraction`、`museum`、`park`、`historical_place`、`religious_place` 等（完整 taxonomy 见 GitHub `OvertureMaps/schema`） |
| **优势** | **GERS 全局唯一 ID**——可与 OSM、Meta、Foursquare 等跨源 join，避免重复 conflation |
| **适合场景** | Trip 项目大规模事实层补充；按城市 bbox 批量拉取，配合 `confidence > 0.7` 过滤 |

### 1.6 OpenStreetMap Overpass API（社区驱动）

| 维度 | 详情 |
|---|---|
| **入口** | `https://overpass-api.de/api/interpreter`（主）+ `https://overpass.kumi.systems/api/interpreter`（备） |
| **数据规模** | 全球，中国区域景点 POI 数万级 |
| **更新频率** | 实时（社区编辑，分钟级反映） |
| **覆盖地区** | 全球；中国一二线城市覆盖较好，三四线及景区细节有缺失 |
| **获取方式** | HTTP POST Overpass QL 查询，无需 API Key |
| **权威性** | 中（社区编辑，质量参差，但开放度最高） |
| **成本** | 免费，ODbL 协议（衍生产品需开源 + attribution） |
| **核心 tag** | `tourism=attraction`、`tourism=museum`、`tourism=gallery`、`tourism=zoo`、`tourism=theme_park`、`historic=*`、`leisure=park`、`name`、`name:en`、`opening_hours`、`website`、`phone`、`wikidata`（关联 Wikidata ID！） |
| **限制** | 单查询建议 timeout ≥60s；高峰期返回慢，建议用 kumi 镜像 |
| **样例查询** | 见下方代码块 |
| **适合场景** | 兜底数据源 + `wikidata` 标签可与 Wikidata 双向 join |

```overpass
[out:json][timeout:120];
area["name"="中国"]["admin_level"="2"]->.searchArea;
(
  node["tourism"~"attraction|museum|gallery|zoo|theme_park"](area.searchArea);
  way["tourism"~"attraction|museum|gallery|zoo|theme_park"](area.searchArea);
);
out center tags;
```

### 1.7 DBpedia（维基百科结构化抽取）

| 维度 | 详情 |
|---|---|
| **入口** | SPARQL `http://dbpedia.org/sparql` |
| **数据规模** | 850M+ 三元组，Place 类 75 万+ 实体 |
| **更新频率** | 季度 snapshot |
| **覆盖地区** | 全球（英文维基为主，多语言章节有独立端点） |
| **获取方式** | SPARQL 端点，REST 风格 API，无需 Key |
| **权威性** | 中-高（从维基百科 infobox 自动抽取，质量受映射质量影响） |
| **成本** | 免费 |
| **核心类** | `dbo:Place`、`dbo:TouristAttraction`、`dbo:Museum`、`dbo:Park`、`dbo:Pyramid`、`dbo:HistoricBuilding` |
| **限制** | Fair Use：10000 行结果、120s 超时、单 IP 50 并发；中文数据不如 Wikidata 全 |
| **适合场景** | 作为 Wikidata 的补充（部分景点 DBpedia 有而 Wikidata 无）；不推荐作为主源 |

---

## 2. 酒店（Hotels）

### 2.1 Overture Maps Places（同上） ⭐ 全球酒店事实层首选

| 关键字段 | 详情 |
|---|---|
| `categories.primary` | `lodging`、`hotel`、`motel`、`hostel`、`bed_and_breakfast`、`resort`、`guest_house`、`vacation_rental` |
| `brand.text` | 连锁品牌（如 "Hilton"、"Marriott"） |
| `confidence` | 0-1 存在置信度，建议过滤 ≥0.7 |
| **优势** | GERS ID 可与 TripAdvisor/Uber/Meta 数据 join |

### 2.2 OpenStreetMap（Overpass） ⭐ 开放度最高

| 维度 | 详情 |
|---|---|
| **核心 tag** | `tourism=hotel/hostel/motel/guest_house/apartment/chalet`、`stars`（星级）、`rooms`（房间数）、`brand`、`operator`、`internet_access`、`phone`、`website`、`opening_hours` |
| **数据规模** | 全球酒店 POI 约 100 万+（中国区域数千到数万） |
| **覆盖地区** | 全球；中国一二线城市覆盖较好 |
| **优势** | 字段最丰富（stars/rooms 等结构化），完全开放 |
| **样例查询** | 见下方代码块 |
| **二次封装工具** | Apify `dataquarry/hotels-lodging`（$3/1000 results，底层是 OSM，已 parse 出 stars/rooms 等字段） |

```overpass
[out:json][timeout:120];
area["name"="上海市"]->.searchArea;
(
  node["tourism"~"hotel|hostel|motel|guest_house"](area.searchArea);
  way["tourism"~"hotel|hostel|motel|guest_house"](area.searchArea);
);
out center tags;
```

### 2.3 Foursquare OS Places（100M+ POI）

| 维度 | 详情 |
|---|---|
| **入口** | https://opensource.foursquare.com/os-places |
| **数据规模** | 100M+ POI，200+ 国家/地区，1000+ 类别 |
| **更新频率** | 周更（每周二发布） |
| **获取方式** | ① HuggingFace：`hf://datasets/foursquare/fsq-os-places/release/dt=2026-06-11/places/parquet/*.parquet`（需注册 HF token）<br>② Foursquare Places Portal（Iceberg catalog + DuckDB/Spark/PyIceberg）<br>③ S3 直读：`s3://fsq-os-places-us-east-1/release/dt=.../places/parquet/*` |
| **权威性** | 高（Foursquare 商业 POI 数据库的开源版） |
| **成本** | 免费，Apache 2.0 |
| **核心字段** | `fsq_place_id`、`name`、`latitude/longitude`、`address`、`locality`、`region`、`postcode`、`country`、`tel`、`website`、`email`、`facebook_id`、`instagram`、`twitter`、`fsq_category_ids`、`fsq_category_labels`（如 `Travel and Transportation > Lodging > Hotel`） |
| **限制** | 2025 年起改为 gated dataset（需注册 HF token 或 Places Portal 账号）；不含星级/房价等动态字段 |
| **适合场景** | 大规模酒店 POI 兜底；与 Overture 互补，cross-validate 提升置信度 |

### 2.4 杭州文化和旅游数据在线（政府权威，仅杭州）

| 维度 | 详情 |
|---|---|
| **入口** | https://data.wgly.hangzhou.gov.cn/ |
| **数据规模** | 4000 万+ 条记录，200+ 关键指标 |
| **更新频率** | 最短 10 分钟/次（实时入住率、景区客流） |
| **覆盖地区** | 杭州全域（含区县） |
| **获取方式** | 网页在线查询 + 即时下载，**无需注册登录** |
| **权威性** | **最高**（杭州市文广旅游局官方，第一财经·新一线城市研究所承建） |
| **成本** | 免费 |
| **核心数据** | ① 重点监测酒店预订率/价格（按经济型/舒适型/高档型/豪华型/民宿分档）<br>② 实时景区客流<br>③ 银联旅游消费<br>④ 航空预订<br>⑤ 历年/区县/假期旅游统计 |
| **酒店特色板块** | "酒店市场分析"主题（与浩华厚海数据平台合作）：供给趋势、商圈热力、品牌渗透、投资热度 |
| **适合场景** | Trip 项目如覆盖杭州，是唯一兼具实时性 + 政府权威的酒店数据源 |

### 2.5 GERS（Overture Global Entity Reference System）—— 跨源酒店 ID 桥接 ⭐ 关键基础设施

| 维度 | 详情 |
|---|---|
| **作用** | 为每个地点分配稳定 UUID，跨 Overture/OSM/Meta/TripAdvisor/Uber 一致 |
| **使用方式** | ① Overture Maps Explorer 在线查询：https://explore.overturemaps.org<br>② Overture 桥接文件（bridge files）做内部 ID 映射<br>③ inHotel 提供 managed GERS API（针对酒旅场景） |
| **对 Trip 项目的价值** | **解决多源去重问题**：高德 POI ID、OSM node ID、Wikidata QID、Overture GERS 四套 ID 通过 GERS 桥接，避免同一酒店在多源中被当作 4 个不同实体 |

### 2.6 不推荐 / 谨慎使用

| 数据源 | 风险 |
|---|---|
| Agoda/Booking.com 官方 API | 严格配额（5000 calls/月，需绑卡），search 端点 10000/天上限，仅返回 5 条评论/地 |
| RealtyAPI（Agoda 包装） | 第三方代理，实时房价/房型/评论齐全但 ToS 灰色，11 个端点，适合原型验证不适合生产 |
| 大众点评/携程直爬 | ToS 明确禁止，法律风险高，**面试被问"数据合规"会翻车** |

---

## 3. 餐厅（Restaurants）

### 3.1 Yelp Open Dataset（学术经典） ⭐ 餐厅评论金标准

| 维度 | 详情 |
|---|---|
| **入口** | https://www.kaggle.com/datasets/yelp-dataset/yelp-dataset |
| **数据规模** | 8 个美国/加拿大都市区，9.29 GB，含 business/checkin/review/tip/user 五个 JSON 文件 |
| **更新频率** | 不定期（最近一次约 4 年前，但仍是学术 benchmark） |
| **覆盖地区** | 美国和加拿大 8 个都市区（不含中国） |
| **获取方式** | Kaggle 注册下载，需同意 Dataset User Agreement |
| **权威性** | 高（Yelp 官方发布，学术界广泛引用） |
| **成本** | 免费 |
| **核心字段** | ① business：`name`、`address`、`city`、`state`、`latitude/longitude`、`stars`（1-5）、`review_count`、`categories`（如 "Restaurants, Italian, Pizza"）、`attributes`（停车/外卖/WiFi/价格区间 `RestaurantsPriceRange2`）、`hours`<br>② review：`text`、`stars`、`date`、`user_id`、`useful/funny/cool`<br>③ checkin：签到时间分布 |
| **限制** | 仅北美 8 城；license 限制学术/研究使用，禁止商用再分发 |
| **适合场景** | Trip 项目做 RAG 评测的"金标准"餐厅评论集；评测召回质量/faithfulness；可作为国内餐厅的对比基线 |

### 3.2 OpenTable 多准则评分数据集

| 维度 | 详情 |
|---|---|
| **入口** | ① Kaggle: https://www.kaggle.com/datasets/irecsys/opentable-data-with-multi-criteria-ratings<br>② IEEE Dataport: https://ieee-dataport.org/documents/opentable-data-multi-criteria-ratings<br>③ GitHub: https://github.com/irecsys/RecData/tree/main/OpenTable |
| **数据规模** | 19536 条评分，1309 个用户，91 家餐厅 |
| **覆盖地区** | 美国（OpenTable 主市场） |
| **获取方式** | 直接下载 CSV |
| **权威性** | 中-高（学术论文配套数据集，arXiv:2501.03072） |
| **成本** | 免费 |
| **核心字段** | `user_id`、`item_id`、`overall_rating`、`food_rating`、`service_rating`、`ambience_rating`、`value_rating`（均为 1-5 分） |
| **优势** | **多准则评分**——比单一 overall rating 更适合做 RAG 评测的多维度召回 |
| **适合场景** | Trip 项目做细粒度餐厅推荐的评测样本（如"环境好的意餐"能否召回 ambience 高的餐厅） |

### 3.3 OpenStreetMap（Overpass）—— 国内餐厅主源 ⭐

| 维度 | 详情 |
|---|---|
| **核心 tag** | `amenity=restaurant/cafe/bar/pub/fast_food`、`cuisine`（如 `chinese`、`regional`、`noodle`、`pizza`）、`name`、`addr:city`、`phone`、`website`、`opening_hours`、`wheelchair` |
| **数据规模** | 全球餐厅 POI 百万级；中国一二线城市数千/城 |
| **覆盖地区** | 全球 |
| **优势** | `cuisine` 字段标准化（OSM Wiki 有完整 taxonomy），完全开放 |
| **样例查询** | 见下方代码块 |
| **二次封装** | Apify `ryanclinton/osm-poi-search`（$1/1000 POI），13 内置类别 + 自定义 tag |

```overpass
[out:json][timeout:120];
area["name"="北京市"]->.searchArea;
(
  node["amenity"~"restaurant|cafe|bar|pub"](area.searchArea);
  way["amenity"~"restaurant|cafe|bar|pub"](area.searchArea);
);
out center tags;
```

### 3.4 Overture Maps Places（同上）—— 餐厅大规模事实层

| 关键 category | `restaurant`、`cafe`、`bar`、`fast_food_restaurant`、`food_court` 等 |

### 3.5 Foursquare OS Places（同上）—— 餐厅补充

| 关键 category_labels | `Dining and Drinking > Restaurant > ...`（细分到菜系，如 Italian、Chinese、Japanese） |

### 3.6 Wikidata / DBpedia（餐厅结构化）

| 数据源 | 类 |
|---|---|
| Wikidata | `wd:Q11707` (Restaurant)、`wd:Q193429` (Café)、`wd:Q19054` (Bar) |
| DBpedia | `dbo:Restaurant` |

---

## 4. 中国本土数据源（综合）

### 4.1 文化和旅游部数据服务栏目（同 1.3）

### 4.2 杭州文化和旅游数据在线（同 2.4）

### 4.3 上海图书馆开放数据平台

| 维度 | 详情 |
|---|---|
| **入口** | https://data.library.sh.cn/ |
| **特色** | 上海地方历史文化景点、名人故居等结构化数据，Linked Data 形式 |
| **适合场景** | 上海深度文化景点的权威描述层补充 |

### 4.4 各地方政府数据开放平台

| 平台 | 入口 | 旅游相关数据集 |
|---|---|---|
| 上海市公共数据开放平台 | https://data.sh.gov.cn | 景区客流、星级酒店名录 |
| 北京市政务数据资源网 | https://data.beijing.gov.cn | A 级景区、文旅活动 |
| 浙江省公共数据开放平台 | https://data.zjzwfw.gov.cn | 全省景区/酒店名录 |
| 贵州省"贵旅查"平台 | （公益平台） | A 级景区、导游资质核验 |

### 4.5 高德开放平台（项目已用，事实层）

| 维度 | 详情 |
|---|---|
| **接口** | `https://restapi.amap.com/v5/place/text`（POI 搜索）、`/v3/place/detail`（详情）、`/v3/assistant/inputtips`（联想） |
| **数据规模** | 中国大陆全量 POI（官方称 3000 万+） |
| **核心字段** | `name`、`typecode`（POI 分类码）、`address`、`location`（GCJ02 坐标）、`tel`、`tag`、`biz_ext.rating`、`biz_ext.cost`（人均消费）、`photos`、`children`（子 POI） |
| **限制** | 免费版 5000 calls/天（个人开发者），企业版可提额；坐标为 GCJ02，需转 WGS84 与 OSM/Overture 对齐 |
| **适合场景** | **保留为事实层主源**（已落地）；新增的多源作为描述层/体验层补充 |

---

## 5. 数据源分级与 Trip 项目落地建议

### 5.1 按"费力程度 / 信息增量 / 合规风险"三维度排序

| 优先级 | 数据源 | 补的层 | 增量价值 | 合规/难度 | 落地动作 |
|---|---|---|---|---|---|
| **P0 必做** | Wikidata + Wikipedia API | 权威描述层 | 高 | 低（开放 API，免费） | 写 `scripts/fetch_wiki.py`，按 spot.name 拉 QID + extract |
| **P0 必做** | 文旅部 5A 名录 | 权威白名单 | 中 | 低（网页爬虫，1s/请求） | 写 `scripts/fetch_mct_5a.py`，生成中国景点白名单 |
| **P1 强烈建议** | Overture Maps Places | 事实层补全 | 高 | 低（S3/DuckDB 免费） | 写 `scripts/fetch_overture.py`，按城市 bbox 批量拉 POI |
| **P1 强烈建议** | OpenStreetMap Overpass | 事实层兜底 | 中-高 | 低（免费，限频） | 写 `scripts/fetch_osm.py`，补 Overture 缺失区域 |
| **P2 评测用** | Yelp Open Dataset | 餐厅评测金标准 | 中（仅北美） | 低（学术 license） | 落到 `eval/fixtures/yelp/`，做召回质量评测 |
| **P2 评测用** | OpenTable 多准则 | 餐厅多准则评测 | 中（小数据集） | 低 | 落到 `eval/fixtures/opentable/` |
| **P3 可选** | Foursquare OS Places | 事实层 cross-validate | 中 | 中（需 HF token） | 与 Overture 做 cross-check，过滤低 confidence POI |
| **P3 可选** | 杭州文旅数据在线 | 实时层（仅杭州） | 高（仅杭州） | 低（无需登录） | 若 Trip 主打杭州则必接，否则跳过 |
| **P3 可选** | DBpedia | 权威描述层补充 | 低 | 低（SPARQL） | Wikidata 没有的景点兜底查 DBpedia |
| **不推荐** | TripAdvisor/大众点评/携程 直爬 | 体验层 | 高 | **高（ToS/法律）** | 改用学术公开数据集或手工抽样 + 标注来源 URL |

### 5.2 数据源 schema 字段对照（针对 Trip 项目 SpotDoc 模型）

按 `docs/rag-multi-source-augmentation.md` §3.1 的 `spot_docs` schema：

```python
# 每条 SpotDoc 需填：
source_type  # "wiki" / "mct" / "overture" / "osm" / "yelp" / "opentable" / "fsq" / "official"
source_name  # "维基百科" / "文化和旅游部" / "Overture Maps" / "OpenStreetMap" / ...
source_url   # 该条数据的原始 URL（如 https://www.wikidata.org/wiki/Q12345）
title        # 景点/酒店/餐厅名
content      # 长文本（百科摘要、UGC 评论等）
chunk_index  # 分块序号
spot_id      # 关联到 spots 表
```

### 5.3 多源 ID 桥接策略（关键！）

| 源 | ID 体系 | 桥接到 GERS 的方式 |
|---|---|---|
| 高德 POI | `poi_id`（字符串） | 通过名称+坐标匹配 Overture GERS（建议用 `name` + 100m 半径 fuzzy match） |
| OpenStreetMap | `node/way id` | Overture 已内置 OSM 桥接（bridge files） |
| Wikidata | `Qxxx` | OSM 的 `wikidata` tag 直接关联；Overture Places 含 `wikidata` 字段 |
| Foursquare | `fsq_place_id` | Overture 与 FSQ 有重叠源（Meta/Microsoft 贡献），可近似 join |
| 文旅部 5A | 无 ID（按名称） | 用高德 inputtips → 名称+城市定位 → 反查 Overture GERS |

**建议在 `spots` 表新增字段**：`gers_id`（VARCHAR，nullable）、`wikidata_id`（VARCHAR）、`osm_id`（VARCHAR），做跨源去重。

### 5.4 分阶段路线图（接续 rag-multi-source-augmentation.md §4）

| 阶段 | 数据源 | 工作量 | 面试含金量 |
|---|---|---|---|
| **P0** | Wikidata + Wikipedia + 文旅部 5A | 1 天 | ★★★ 合规、易讲、增量明显 |
| **P1** | Overture Places 按城市 bbox 批量补 POI 事实层 | 0.5-1 天 | ★★★★ 大规模真实数据，GERS 跨源 ID 是亮点 |
| **P2** | OSM Overpass 兜底 + Foursquare cross-validate | 1 天 | ★★★ 多源融合，confidence 加权 |
| **P3** | Yelp/OpenTable 评测集 + ragas Faithfulness | 1 天 | ★★★★ 评测闭环，回应"RAG 真的带来模型外信息吗" |

---

## 6. 关键链接速查

### 6.1 数据下载 / API 端点

| 数据源 | 入口 |
|---|---|
| Wikidata SPARQL | https://query.wikidata.org/sparql |
| Wikidata Query UI | https://query.wikidata.org/ |
| Wikipedia API | https://zh.wikipedia.org/w/api.php |
| 文旅部数据服务 | https://sjfw.mct.gov.cn/ |
| 文旅部 5A 景区列表 | https://sjfw.mct.gov.cn/site/dataservice/rural?type=10 |
| 长三角 5A 景区数据集 | https://www.geodata.cn/main/face_science_detail?guid=129215637810316 |
| Overture Maps 下载 | https://overturemaps.org/download/ |
| Overture Maps Explorer | https://explore.overturemaps.org |
| Overture S3 路径 | `s3://overturemaps-us-west-2/release/2026-06-17.0/theme=places/type=place/*` |
| OSM Overpass 主端点 | https://overpass-api.de/api/interpreter |
| OSM Overpass 备用 | https://overpass.kumi.systems/api/interpreter |
| OSM Overpass Turbo（可视化） | https://overpass-turbo.eu/ |
| OSM Map Features 文档 | https://wiki.openstreetmap.org/wiki/Map_features |
| Foursquare OS Places | https://opensource.foursquare.com/os-places |
| Foursquare HF 数据集 | https://huggingface.co/datasets/foursquare/fsq-os-places |
| Foursquare Places Portal | https://docs.foursquare.com/data-products/docs/access-fsq-os-places |
| DBpedia SPARQL | http://dbpedia.org/sparql |
| Yelp Open Dataset | https://www.kaggle.com/datasets/yelp-dataset/yelp-dataset |
| OpenTable Kaggle | https://www.kaggle.com/datasets/irecsys/opentable-data-with-multi-criteria-ratings |
| OpenTable IEEE Dataport | https://ieee-dataport.org/documents/opentable-data-multi-criteria-ratings |
| OpenTable GitHub | https://github.com/irecsys/RecData/tree/main/OpenTable |
| 杭州文旅数据在线 | https://data.wgly.hangzhou.gov.cn/ |
| 上海图书馆开放数据 | https://data.library.sh.cn/ |
| 上海市公共数据 | https://data.sh.gov.cn |
| 北京市政务数据 | https://data.beijing.gov.cn |
| 浙江省公共数据 | https://data.zjzwfw.gov.cn |

### 6.2 工具/CLI

| 工具 | 用途 |
|---|---|
| `pip install overturemaps` | Overture 官方 CLI，按 bbox 下载 GeoJSON/GeoParquet |
| DuckDB + `LOAD spatial; LOAD httpfs;` | 直接 SQL 查询 Overture/Foursquare 的 S3 parquet |
| `pip install SPARQLWrapper` | Python 查 Wikidata/DBpedia SPARQL 端点 |
| Overpass Turbo | 在线可视化 + 调试 Overpass QL |
| Overture Maps Explorer | 在线浏览 + 区域下载 |

### 6.3 许可证速查

| 数据源 | 许可证 | 商用 | 衍生产品开源要求 |
|---|---|---|---|
| Wikidata | CC0 | ✅ | ❌ |
| Wikipedia | CC BY-SA 3.0 | ✅ | ✅（衍生作品同协议） |
| 文旅部数据 | 政府公开信息 | ✅（标注来源） | ❌ |
| Overture Places | CDLA Permissive v2.0 | ✅ | ❌（OSM 衍生部分需 ODbL attribution） |
| OpenStreetMap | ODbL | ✅ | ✅（衍生数据库需同协议） |
| Foursquare OS Places | Apache 2.0 | ✅ | ❌ |
| Yelp Open Dataset | 学术研究用 | ❌（禁商用再分发） | — |
| OpenTable 多准则 | 学术研究用（IEEE Dataport） | ❌ | — |
| DBpedia | CC BY-SA 3.0 | ✅ | ✅ |

---

## 7. 风险与注意事项

1. **坐标系统一**：高德是 GCJ02，OSM/Overture/Wikidata 是 WGS84，Foursquare 通常是 WGS84。入库前必须统一转 WGS84（用 `coordtransform` 库），否则地图可视化会偏移 50-500 米。
2. **同名消歧**：百科/OSM 对齐 spots 时用"名称 + 城市"双键；同名景点（如"西湖"在多个城市都有）必须用坐标 + 行政区双校验。
3. **Chroma 向量维度一致**：所有源的文本分块后都用 `bge-small-zh-v1.5`（384 维）embedding，不可混模型。
4. **限频合规**：
   - Wikidata SPARQL：单 IP 100 req/s，但复杂查询 120s 超时
   - Overpass：建议 `timeout=120`，单查询不超过 10M 元素
   - Wikipedia API：User-Agent 必填，建议 1 req/s
   - 文旅部网页：1 req/s，robots.txt 遵守
5. **GERS 桥接的近似性**：名称+坐标 fuzzy match 会有 5-10% 错配率，需人工抽检；建议先用 5A 名录做小规模验证。
6. **Yelp/OpenTable 仅北美**：作为评测金标准，不是生产数据源；面试讲"用了公开学术数据集做评测"是加分项。
7. **Foursquare gated 化**：2025 年起需 HF token 或 Places Portal 注册，但仍免费；若担心未来收紧，优先押注 Overture。

---

## 8. 面试话术：把多源讲成亮点

**30 秒版：**
> 知识库我做了**事实层 + 文本层**的多源异构架构。事实层主源是高德 POI（保证名称/坐标/品类的中国本土权威），同时引入 Overture Maps Places（70M+ 全球 POI，CDLA Permissive 开放协议）和 OpenStreetMap Overpass 做兜底与 cross-validate，用 Overture 的 GERS 全局 ID 做跨源去重——高德 poi_id、OSM node id、Wikidata QID 三套 ID 通过 GERS 桥接，避免同一酒店被当 4 个不同实体。文本层是 Wikidata/Wikipedia 的权威描述 + 文旅部 5A 名录的白名单背书 + Yelp/OpenTable 公开学术数据集做评测金标准。所有源都打了 `source_type` 血缘标签，检索时按来源可靠度加权 RRF 融合，Cross-Encoder 重排把真实来源片段喂进去。这样 RAG 才真正带来模型参数外的新信息，而不是把模型自己编的内容喂回给自己。合规上严格守线——只用开放授权数据，不碰大众点评/携程直爬。

**加分心机：**
- "GERS 是 Overture Maps Foundation 推的全局地点 ID 标准，AWS/Meta/Microsoft/TomTom/Tripadvisor/Uber 都在用，我把它作为多源去重的 backbone，这是面向未来的设计。"
- "Wikidata 的 `wikidata` tag 在 OSM 里也有，三源通过 QID 天然 join，这是为什么我没选 DBpedia 做主源——Wikidata 的生态连接性更好。"
- "评测用 Yelp Open Dataset 这种学术 benchmark 而不是自爬数据，是因为它的 license 明确允许学术研究使用，面试讲合规不会翻车。"

---

## 附录 A：快速启动脚本骨架

```python
# scripts/fetch_overture.py（P1 阶段骨架）
import subprocess
import json
from pathlib import Path

CITIES = {
    "上海": [120.85, 30.67, 122.24, 31.87],
    "北京": [115.42, 39.42, 117.51, 41.06],
    # ... 更多城市 bbox
}

def fetch_overture_places(city: str, bbox: list, out_dir: Path):
    """按城市 bbox 拉取 Overture Places，输出 GeoJSON"""
    out_file = out_dir / f"{city}_places.geojson"
    cmd = [
        "overturemaps", "download",
        "--bbox", ",".join(str(x) for x in bbox),
        "-f", "geojson",
        "--type", "place",
        "-o", str(out_file),
    ]
    subprocess.run(cmd, check=True)
    return out_file

def filter_tourism_related(geojson_path: Path) -> list:
    """过滤景点/酒店/餐厅相关 category"""
    data = json.loads(geojson_path.read_text())
    keep_categories = {
        "tourist_attraction", "museum", "park", "historical_place", "religious_place",
        "lodging", "hotel", "motel", "hostel", "resort", "guest_house",
        "restaurant", "cafe", "bar", "fast_food_restaurant",
    }
    return [
        f for f in data["features"]
        if f["properties"].get("categories", {}).get("primary") in keep_categories
        and f["properties"].get("confidence", 0) >= 0.7
    ]

if __name__ == "__main__":
    out_dir = Path("data/overture_raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    for city, bbox in CITIES.items():
        geojson = fetch_overture_places(city, bbox, out_dir)
        filtered = filter_tourism_related(geojson)
        (out_dir / f"{city}_filtered.json").write_text(
            json.dumps(filtered, ensure_ascii=False, indent=2)
        )
        print(f"{city}: {len(filtered)} POIs")
```

```python
# scripts/fetch_wikidata.py（P0 阶段骨架）
from SPARQLWrapper import SPARQLWrapper, JSON

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

def fetch_china_attractions(limit: int = 5000):
    """查询中国所有旅游景点（含坐标、图片、描述）"""
    query = f"""
    SELECT ?item ?itemLabel ?itemDescription ?coord ?image ?website WHERE {{
      ?item wdt:P31/wdt:P279* wd:Q570116.
      ?item wdt:P17 wd:Q148.
      OPTIONAL {{ ?item wdt:P625 ?coord. }}
      OPTIONAL {{ ?item wdt:P18 ?image. }}
      OPTIONAL {{ ?item wdt:P856 ?website. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en". }}
    }}
    LIMIT {limit}
    """
    sparql = SPARQLWrapper(SPARQL_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    return sparql.query().convert()
```

---

> 维护：本清单随数据源政策变化需定期复核（建议每季度）。重点关注：① Overture 月度发布；② Foursquare gated 化是否进一步收紧；③ 文旅部数据服务栏目是否推出 API；④ GERS 是否成为 OGC 标准。
