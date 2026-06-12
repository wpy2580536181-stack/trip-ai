# Trip — AI 智能旅行规划系统

基于 AI 的景点介绍与行程规划系统，用户可输入目的地、预算和天数，AI 自动生成完整的旅行计划，并支持对话式交互。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Vant 4 |
| 后端 | Express 5 + TypeScript |
| 数据库 | MySQL + Prisma ORM |
| AI | LangChain + DeepSeek/Kimi API |

## 项目结构

```
trip/
├── trip-front/                  # 前端
│   └── src/
│       ├── api/                 # API 调用层（request.ts + 业务接口）
│       ├── components/          # 通用组件
│       ├── config/              # 前端配置（城市列表等）
│       ├── router/              # 路由配置 + 导航守卫
│       ├── views/               # 页面组件
│       ├── styles/              # 全局样式
│       └── utils/               # 工具函数
│
└── trip-server/                 # 后端
    └── src/
        ├── config/              # 配置（JWT、数据库）
        ├── controllers/         # 控制器（请求处理、参数校验、响应格式化）
        ├── middleware/           # 中间件（认证、鉴权）
        ├── prompts/             # AI Prompt 模板
        ├── routes/              # 路由定义（中间件编排 + 派发到 controller）
        ├── services/            # 业务逻辑层
        └── utils/               # 工具函数
```

## 前置条件

- Node.js >= 18
- MySQL >= 8.0
- 一个兼容 OpenAI 的 LLM API Key（DeepSeek / Kimi）

## 快速开始

### 1. 克隆并安装依赖

```bash
cd trip-server && npm install
cd ../trip-front && npm install
```

### 2. 配置环境变量

```bash
cp trip-server/.env.example trip-server/.env
```

编辑 `trip-server/.env`，填写实际的数据库连接和 API Key。

### 3. 初始化数据库

```bash
cd trip-server
npx prisma db push          # 创建数据库表
npm run seed                 # 初始化角色数据（ADMIN/USER）
```

### 4. 启动服务

```bash
# 终端 1 — 后端（端口 3000）
cd trip-server && npm run dev

# 终端 2 — 前端（端口 5173）
cd trip-front && npm run dev
```

访问 http://localhost:5173

## 环境变量

### 后端（trip-server/.env）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | MySQL 连接字符串 | — |
| `JWT_SECRET` | JWT 签名密钥 | —（必填） |
| `JWT_EXPIRES_IN` | Token 过期时间 | `7d` |
| `PORT` | 服务端口 | `3000` |
| `CORS_ORIGIN` | 允许的前端域名 | `http://localhost:5173` |
| `MODEL_PROVIDER` | AI 模型提供商 | `DEEPSEEK` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | — |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-chat` |
| `KIMI_API_KEY` | Kimi API Key | — |
| `KIMI_BASE_URL` | Kimi API 地址 | `https://api.kimi.cn/v1` |
| `KIMI_MODEL` | Kimi 模型名 | `kimi-for-coding` |

### 前端（trip-front/.env — 可选）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `VITE_API_TARGET` | API 代理目标地址 | `http://localhost:3000` |

## API 接口

### 健康检查

```
GET /api/test
```

### 用户

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| POST | `/api/user/register` | 注册 | — |
| POST | `/api/user/login` | 登录（支持用户名或邮箱） | — |
| GET  | `/api/user/info` | 获取用户信息 | 需 token |
| PUT  | `/api/user/info` | 更新用户资料 | 需 token |
| PUT  | `/api/user/password` | 修改密码 | 需 token |
| POST | `/api/user/forgot-password` | 获取密码重置验证码 | — |
| POST | `/api/user/reset-password` | 重置密码（需验证码） | — |

### 行程

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/trip/recommend` | AI 生成行程规划 |
| POST | `/api/trip/chat` | AI 对话（SSE 流式响应） |

## 脚本

### trip-server

| 命令 | 说明 |
|---|---|
| `npm run dev` | 开发模式（nodemon + ts-node） |
| `npm run build` | 编译 TypeScript |
| `npm start` | 启动编译后的代码 |
| `npm run seed` | 初始化角色数据 |
| `npm run migrate` | 同步数据库表结构 |

### trip-front

| 命令 | 说明 |
|---|---|
| `npm run dev` | 启动 Vite 开发服务器 |
| `npm run build` | 构建生产版本 |
| `npm run preview` | 预览生产构建 |
| `npm run format` | 格式化代码 |

## 安全说明

- JWT Secret 必须通过 `JWT_SECRET` 环境变量设置，无硬编码 fallback
- 密码重置使用 UUID token，30 分钟有效，单次使用
- 登录、注册、密码重置接口均有频率限制（15 分钟 10 次）
- `.env` 文件已被 `.gitignore` 排除，请勿提交真实密钥

## Phase 1a：AI Agent + RAG + 对话记忆

Phase 1a 在原有基础上引入了 RAG 知识库、对话记忆、Agent 工具调用和容错降级。

### 新增能力

- **RAG 知识库**：基于 Chroma 向量数据库 + bge-small-zh 中文 embedding 模型
- **Agent 编排**：LangChain Tool Calling Agent，自主决定调用 `retrieve_knowledge` 工具
- **对话记忆**：所有对话持久化到 MySQL，Agent 自动加载历史上下文（最近 10 轮）
- **Tool 容错**：超时、重试、降级——Chroma 不可用时自动降级到 MySQL
- **对话 / 行程历史接口**：列出、查看、删除用户的对话和行程

### 新增数据表

- `trips` — 用户行程历史（含 `parent_trip_id` 自引用，支持 Phase 2 行程优化版本链）
- `conversations` — 对话会话（含 `summary` 字段，Phase 1b 用于滑动窗口摘要压缩）
- `messages` — 对话消息（`onDelete: Cascade` 关联 conversations）
- `spots` — 景点知识库（`vector_id` 关联 Chroma）

### 新增 API

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| POST | `/api/trip/chat` | AI 对话（流式，需登录，持久化） | 需 |
| GET | `/api/conversations` | 对话列表 | 需 |
| GET | `/api/conversations/:id` | 对话详情 | 需 |
| DELETE | `/api/conversations/:id` | 删除对话 | 需 |
| GET | `/api/history/trips` | 行程历史 | 需 |
| GET | `/api/history/trips/:id` | 行程详情 | 需 |

### 启动 Chroma（必需）

Chroma 是 RAG 的核心依赖，必须先启动：

```bash
# 方式 1：pip 安装
pip install chromadb
chroma run --path ./trip-server/chroma_data --host 127.0.0.1 --port 8000

# 方式 2：Docker
docker run -d --name chroma -p 8000:8000 \
  -v $(pwd)/trip-server/chroma_data:/chroma/.chroma \
  chromadb/chroma
```

### 导入知识库

```bash
cd trip-server
npm run seed:knowledge
```

首次运行会下载 bge-small-zh 模型（约 100MB），需要 1-2 分钟。导入成功后输出类似：

```
>>> 导入 chengdu.json (10 个景点)...
   成功: 10, 失败: 0
```

### 新增环境变量

在 `trip-server/.env` 中追加：

```bash
# Chroma 向量数据库
CHROMA_URL=http://localhost:8000

# HuggingFace 模型下载镜像（默认走国内镜像；海外可改为 https://huggingface.co/）
HF_ENDPOINT=https://hf-mirror.com/
```

### 数据同步机制

知识库采用 **MySQL 为权威源 + Chroma 事务性同步** 模式：

- 创建景点：先写 MySQL，成功后再写 Chroma；Chroma 失败则回滚 MySQL
- 检索景点：优先 Chroma 相似度搜索；Chroma 不可用或为空时降级到 MySQL `findMany`（按 `rating` 降序）
- `retrieve_knowledge` 工具对 RAG 调用有 8s 超时 + 1 次重试 + 降级提示
