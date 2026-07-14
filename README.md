# Trip — AI 智能旅行规划系统

基于 AI 的景点介绍与行程规划系统，输入目的地、预算和天数，AI 自动生成完整旅行计划，并支持对话式交互。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Naive UI |
| 后端 | FastAPI (Python 3.12+) |
| 数据库 | MySQL + SQLAlchemy (async) + ChromaDB (向量) |
| AI | LangChain + DeepSeek API |

## 功能

- **AI 行程生成** — 输入目的地/预算/天数，自动生成每日行程（含景点、餐饮、住宿）
- **对话式交互** — 与 AI 助手多轮对话，调整行程细节
- **高德地图 MCP 集成** — 通过 MCP 协议实时查询高德全库 POI
- **多维度检索** — 向量 (bge-small-zh) + 关键词 + 热度 三路召回，Cross-Encoder (bge-reranker) 重排序
- **行程度量** — 预算明细、出行 Tips
- **三层 RAG 评估体系** — 检索层 (Hit@K/MRR) + 生成层 (Faithfulness/Relevancy) + 线上反馈

## 界面预览

### 首页 — 行程生成

![首页](screenshots/home.png)

### 对话页 — AI 交互

![对话](screenshots/chat.png)

### 行程详情 — 每日行程

![行程详情](screenshots/detail.png)

### 地图 — 景点定位

![地图](screenshots/map.png)

## 快速开始

### 前置条件

- Python >= 3.12
- MySQL >= 8.0
- ChromaDB（向量数据库）
- DeepSeek API Key

### 启动步骤

```bash
# 1. 安装后端依赖
cd trip-backend
uv sync

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入数据库连接和 API Key

# 3. 启动 Chroma（二选一）
pip install chromadb && chroma run --path ./chroma_data --host 127.0.0.1 --port 8000
# 或 docker run -d --name chroma -p 8001:8000 chromadb/chroma

# 4. 初始化数据库表
uv run python create_tables.py

# 5. 启动
# 终端 1 - 后端 (端口 8000)
cd trip-backend && uv run uvicorn src.main:app --reload
# 终端 2 - 前端 (端口 5173)
cd trip-front && npm install && npm run dev
```

访问 http://localhost:5173

## API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/user/register` | 注册 |
| POST | `/api/user/login` | 登录 |
| GET/PUT | `/api/user/info` | 用户信息 |
| POST | `/api/trip/recommend` | AI 生成行程 |
| POST | `/api/trip/optimize` | AI 优化行程 |
| POST | `/api/trip/chat` | AI 对话（SSE 流式） |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/history/trips` | 行程历史 |
| GET/POST | `/api/feedback` | 用户反馈 |
| GET | `/api/feedback/admin/daily-stats` | 反馈统计趋势（admin） |
| GET | `/api/feedback/admin/high-token-low-satisfaction` | 高分低满意度案例（admin） |
| GET | `/api/knowledge/spots` | 景点列表 |
| GET | `/api/stats/token-usage/summary` | Token 使用统计 |
| GET | `/api/admin/agent-trace` | Agent 执行轨迹（admin） |
| GET | `/api/admin/mcp-stats` | MCP 进程监控（admin） |
| GET | `/health` | 健康检查 |

## 项目结构

```
trip/
├── trip-front/          # 前端 (Vue 3)
│   └── src/
│       ├── views/       # 页面组件
│       ├── components/  # 通用组件
│       └── api/         # API 调用层
├── trip-backend/      # 后端 (FastAPI)
│   └── src/
│       ├── controllers/ # 路由/控制器
│       ├── services/    # 业务逻辑（Agent/RAG/LLM）
│       │   └── rag/     # RAG 检索管线
│       │   └── mcp/     # MCP 工具集成
│       ├── middleware/  # 中间件（认证/限流/幂等/并发）
│       ├── models/      # SQLAlchemy 数据模型
│       └── eval/        # Agent & RAG 评估框架
│           ├── fixtures/    # 测试用例（YAML）
│           ├── evaluators/  # 评估器（13+3 个）
│           └── retrieval/   # 检索层评估（Hit@K/MRR）
└── docs/                # 设计文档

## 知识库 RAG

- **数据规模**：30,784 条 POI 数据，覆盖 343+ 个地级市（热门旅游城市各 ~450 条）
- **数据来源**：手工整理（`data/spots/`）+ 高德地图 API 批量拉取（`scripts/seed-poi-*.ts`）
- **实时补充**：Amap MCP `maps_text_search` 在 agent 规划时可实时查询高德全库 POI（千万级）
- **检索链路**（~640ms P50）：本地关键词改写 → Chroma 向量 / MySQL 关键词 / 评分 三路召回 → RRF 融合 → Cross-Encoder 重排
- **检索优化**：本地关键词提取替代 LLM 改写（省 ~800ms）+ 高分命中跳过重排
- **Embedding**：bge-small-zh-v1.5（本地，512 维，~50ms/次）
- **重排序**：bge-reranker-base Cross-Encoder（top-20）
- **存储**：MySQL（关系索引）+ ChromaDB（向量索引，~23 MB）

## RAG 评估体系

项目内置三层 RAG 评估体系，覆盖检索、生成和线上三个维度：

| 层级 | 指标 | 说明 |
|------|------|------|
| 检索层 | Hit@K（K=1/3/5/10/20）、MRR | 量化检索召回质量和排序效果 |
| 生成层 | Faithfulness、Answer Relevancy | LLM-as-Judge 自动评分，衡量幻觉和相关性 |
| 线上 | 点赞/点踩率、高分低满意度 | 复用 Feedback 系统，持续追踪用户真实体验 |

```bash
# 运行评估
cd trip-backend
uv run python -m eval.run                       # Agent 评估（mock）
uv run python -m eval.run --real --tag smoke     # Agent 评估（真实后端）
uv run python -m eval.retrieval.run              # 检索层评估
```

## 项目说明

该项目为个人学习项目，用于探索 LLM、RAG 和流式交互在旅行规划场景中的应用。

