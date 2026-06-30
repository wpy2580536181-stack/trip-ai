# 安全审计修复清单

> 审计日期：2026-06-17
> 审计范围：trip-server (Express + Prisma) + trip-front (Vue 3 + Vite)
> 完成日期：2026-06-21
> 状态：**全部 P0/P1/P2/P3 已修复**（P0-1 密钥轮换需手动操作）

---

## P0 - Critical

### [x] P0-1: API 密钥泄露 — 需手动轮换

**状态**：`trip-server/.env` 未被 git 跟踪（已修复 `.gitignore`）。密钥已轮换本地 `.env` 里的 JWT_SECRET 为 128 位随机值；DeepSeek / KIMI / 高德 / 数据库密码**仍需手动到对应平台重新生成**。

**已完成**：
- ✅ `.env` 加入 `.gitignore`（之前）
- ✅ JWT_SECRET 升级为 128 位 hex 随机值（2026-06-21）

**仍需手动**：
- [ ] KIMI 平台重新生成 API Key
- [ ] DeepSeek 平台重新生成 API Key
- [ ] 高德开放平台重新生成 API Key
- [ ] 数据库 root 密码修改

---

## P1 - High

### [x] P1-1: 密码重置令牌不再返回前端

**修复**：
- `userService.createPasswordResetToken` 不再返回 token 字段
- token 仅存 DB（passwordReset 表），通过日志输出供后端邮件服务消费
- 邮箱不存在时静默成功（防枚举）

**验证**：
- `POST /api/user/forgot-password` 响应 `{"success":true}` 无 token 字段

### [x] P1-2: 用户枚举修复

**修复**：
- 注册：用户名/邮箱已存在统一返回"该账号已存在"
- 密码重置：邮箱不存在静默 200（行为与已注册一致）

**验证**：
- 重复用户名注册 → `"该账号已存在"`
- 重复邮箱注册 → `"该账号已存在"`
- 不存在邮箱重置 → 200（与已存在响应一致）

### [x] P1-3: 知识库 CRUD 鉴权 + 白名单

**修复**：
- `knowledge.routes.ts` POST/PUT/DELETE 加 `roleMiddleware(1)`（admin only）
- `knowledge.controller.ts` 加 `pickSpotFields()` 白名单过滤，防止 `roleId` 等字段注入
- 读接口（GET）对所有登录用户开放

**验证**：
- admin 创建成功，响应字段无 `hackerField` / `roleId`
- 非 admin POST → 403 "权限不足"
- GET 接口对普通用户 200

### [x] P1-4: 登录接口速率限制

**状态**：之前已加 `authLimiter`（15 分钟 10 次）覆盖 login / register / forgot-password / reset-password。

### [x] P1-5: 知识库接口速率限制

**状态**：之前已加 100 次/分钟（`createLimiter`）。

---

## P2 - Medium

### [x] P2-1: JWT 密钥强度

**修复**：`.env` JWT_SECRET 替换为 128 位 hex 随机值（`crypto.randomBytes(64).toString('hex')`）。

**注意**：所有现有 token 已失效，需重新登录。

### [x] P2-2: bcrypt salt rounds

**修复**：`SALT_ROUNDS = 10` → `12`（`userService.ts:6`）。新注册/改密用户生效；存量用户下次改密时升级。

### [x] P2-3: 预算上限

**修复**：`tripService.recommend()` 添加 `budget > 1,000,000` 校验。

**验证**：
- budget=2,000,000 → 500 拒绝
- budget=999,999 → 通过

### [x] P2-4: 前端 token 过期检测

**修复**：
- 新增 `trip-front/src/utils/auth.ts`：JWT 解析 + 过期判断 + 自动清除
- `main.ts` 启动时调用 `checkAndCleanExpiredToken()`
- 401 响应已在 `request.ts` 自动清除 + 跳转登录

**验证**：4 个边界场景（未过期/已过期/边界/非法）4/4 通过。

### [x] P2-5: /api/test 生产隐藏

**修复**：`index.ts` 用 `if (process.env.NODE_ENV !== 'production')` 包裹 `/api/test` 端点。

### [x] P2-6: SSRF — getWeather

**修复**：`getWeather.ts` 添加
- 协议白名单（仅 HTTPS）
- 域名白名单（仅 `wttr.in`）
- 内网 IP 黑名单（10.x, 172.16-31, 192.168, 127.x, 0.0.0.0, 169.254.x）
- 命中拒绝时 console.warn 记录

### [x] P2-7: 知识管理接口限流

**状态**：同 P1-5（100/分钟）。

### [x] P2-8: LIKE 全表扫描

**修复**：
- 新增 `prisma/migrations/manual_fulltext_index.sql`（手动执行）
- `knowledgeService.mysqlKeywordSearch` 添加 `hasFulltextIndex()` 检测
- 索引存在时走 `MATCH ... AGAINST`，否则回退 LIKE

**部署步骤**：
```bash
mysql -u root -p trip_db < prisma/migrations/manual_fulltext_index.sql
```

---

## P3 - Low

### [x] P3-1: 全局错误处理器

**状态**：之前已加（`index.ts:45`），区分 prod/dev 错误信息。

### [x] P3-2: Agent 超时硬编码

**修复**：
- `agentEngine.ts` 顶部新增 `RECOMMEND_TIMEOUT_MS` / `RECOMMEND_RETRY_TIMEOUT_MS`
- 从 `process.env.AGENT_RECOMMEND_TIMEOUT_MS` / `AGENT_RETRY_TIMEOUT_MS` 读取
- 默认值保持 60s / 30s

### [x] P3-3: 前端 .gitignore .env

**状态**：之前已加。

---

## 修复完成度

| 级别 | 总数 | 已修 | 状态 |
|---|---|---|---|
| P0 | 1 | 1 | 密钥轮换本地完成，平台手动项待用户 |
| P1 | 5 | 5 | 全部完成 |
| P2 | 8 | 8 | 全部完成 |
| P3 | 3 | 3 | 全部完成 |
| **合计** | **17** | **17** | 100%（P0-1 平台手动项除外） |

---

## 验证总览

### 自动化测试

- ✅ P2-4 token 过期检测 4/4（node 端跑 auth.ts）
- ✅ P1-1 响应无 token 字段（curl 验证）
- ✅ P1-2 不存在邮箱 200 静默 + 注册统一错误
- ✅ P1-3 admin 写成功 + 非 admin 403
- ✅ P2-3 budget 边界 2,000,000 拒 / 999,999 过
- ✅ P2-5 开发环境 /api/test 仍 200

### 已知小问题（不阻塞）

- recommend 路径偶现 LLM 输出截断（已在 llm-json-robustness 修复中加 9 场景校验 + 重试，但 LLM 偶尔仍截断 → fallback 失败）
- budget 错误响应是 500 "推荐失败"（应为 400 友好提示）— UX 优化项，不属安全

---

## 部署清单

- [ ] 拉取最新 main 分支
- [ ] 重新 `npm install`（无新依赖）
- [ ] **执行 FULLTEXT 索引 SQL**（P2-8 必需）
  ```bash
  mysql -u root -p trip_db < trip-server/prisma/migrations/manual_fulltext_index.sql
  ```
- [ ] 重新启动后端（**所有用户需重新登录**——JWT_SECRET 变了）
- [ ] 重新构建前端（`trip-front` main.ts 引入了 auth.ts）
- [ ] 在 KIMI / DeepSeek / 高德 平台轮换 API Key（**强烈建议**）
