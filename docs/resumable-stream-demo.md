# 断点续传流式 Agent · Demo 指南

> 配套文件：`docs/resumable-demo.html`
> **前置**：trip-server 在 3000 端口运行

## 快速开始

### 1. 启动后端

```bash
cd trip-server
# 1) 启 Redis（如果没起）
docker ps | grep trip-redis || docker start trip-redis

# 2) 启后端
npx ts-node src/index.ts
# 等看到 "Server running on http://localhost:3000"
```

### 2. 启动 demo 静态服务

**重要**：demo HTML 内部用**绝对 URL** `http://localhost:3000/api/...`，后端 CORS allowlist 已 merge 以下 origin（不需要任何配置）：

| Origin | 场景 | 启动方式 |
|---|---|---|
| `http://localhost:5173` | trip-front Vite dev | `cd trip-front && npm run dev` + 放 `public/` |
| `http://localhost:8080` | 任意静态 server | `cd docs && python3 -m http.server 8080` |
| `http://localhost:3000` | 后端同源 | 需 `express.static` 配（暂未） |
| `null` | **双击 file:// 打开** | 浏览器直接打开 `docs/resumable-demo.html` |

**最简单（推荐）**：

```bash
# 终端 1：后端
cd trip-server && npx ts-node src/index.ts

# 浏览器（直接双击或拖到浏览器）：
open docs/resumable-demo.html
# file:// 协议下 Origin 是 'null'，后端 CORS allowlist 已含 'null'
```

> **生产环境安全**：设 `CORS_DEMO=0` 禁用 demo 默认 origin，只用 `CORS_ORIGIN` env 配。
> 例如 `.env` 里：
> ```
> CORS_ORIGIN=https://your-production-domain.com
> CORS_DEMO=0
> ```

### 3. 打开 demo

浏览器访问 `http://localhost:8080/resumable-demo.html`

**账号**：`eval-test` / `EvalTest@2026`（首字母大写 E T 0，密码中间是大写 T）
**如果登录失败**：先打开 DevTools → Network 标签，看 `/api/user/login` 请求状态码
- 404 → 后端没启或端口不对
- CORS error → 端口不在 allowlist，看上面配置
- 401 → 密码错，**注意是 `EvalTest@2026` 不是 `Evaltest@2026`**

## 测试场景

### 场景 A：完整流式输出

1. **登录**：点击"登录"按钮（用 `eval-test` 账号）
2. **发送**：点击"发送"
3. 观察：
   - 状态栏：`空闲` → `流式中...` → `完成`
   - AI bubble 逐渐填充内容
   - 事件日志：绿色 `CHUNK` 标签持续输出
   - 统计：`chunks 收到` 数字累加
   - 统计：`当前 lastSeq` 持续递增
   - 统计：`streamId` 在 header 返回后显示

**预期**：~30 秒后整个回复渲染完，状态变为"完成"。

### 场景 B：模拟断网 → 自动重连

1. 完成场景 A 的登录和首次发送
2. 在流式输出**中途**点击"模拟断网"（建议在 5-10 个 chunk 后）
3. 观察：
   - 状态栏：`流式中...` → `已断开，等待重连...` → `网络中断，重连中 (1/5)...` → 继续
   - 事件日志：`INFO 模拟断网 → abort` + `RESUME 第 1/5 次重连...`
4. **关键观察**：
   - 重连请求的 header 应包含 `X-Stream-Id: stream:xxx` 和 `Last-Event-ID: N`
   - 状态栏会显示重试次数

**预期**：由于 server 端也会检测到 client socket 关闭并 abort agent，重连后拿到的内容有限（abort 前的 event）。这是已知设计权衡，详见 `streamable-agent-resumable.md` 的"已知设计权衡"。

### 场景 C：手动续传（URL 持久化场景）

1. 完成场景 A，记下状态栏的 `streamId` 和 `lastSeq`
2. **刷新浏览器**（模拟用户重新打开页面）
3. 重新登录（localStorage 存了 token，会自动恢复）
4. **修改**：直接调用后端 API（用 browser DevTools console）：

```javascript
// 在浏览器 console 跑
const res = await fetch('/api/trip/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + localStorage.getItem('trip_demo_token'),
    'X-Stream-Id': 'stream:PASTE_STREAM_ID_HERE',
    'Last-Event-ID': 'PASTE_LAST_SEQ_HERE',
  },
  body: JSON.stringify({ message: 'x', conversationId: null }),
})
const reader = res.body.getReader()
const decoder = new TextDecoder()
while (true) {
  const { done, value } = await reader.read()
  if (done) break
  console.log(decoder.decode(value))
}
```

5. 观察 console：会看到 server 从 Redis 重发 lastSeq 之后的所有 events + `event: end`

**预期**：完整看到从断点开始的剩余内容，**字节级一致**于原始 stream。

## 进阶调试

### 查看 Redis 中的 stream 数据

```bash
# 进入 Redis
docker exec -it trip-redis redis-cli

# 看所有 stream keys
KEYS stream:*

# 看某个 stream 的元数据
HGETALL stream:xxx

# 看 events 列表（stream:{id}:events）
LRANGE stream:xxx:events 0 -1

# 看当前 seq 计数
GET stream:xxx:seq

# 看 TTL
TTL stream:xxx
```

### 后端日志观察

后端日志（pino pretty）会显示：
- `DEBUG Stream created` — streamStore 创建
- `WARN 写入失败，已中止 Agent` — client socket 关闭触发 abort
- `INFO 续传完成 lastSeq=N count=N status=...` — 续传路径走通

### 调整重连退避

如果想测"长退避"（看 1s/2s/4s 退避效果），修改 demo HTML：

```javascript
// 找到 fetchStreamDemo 调用
currentController = await fetchStreamDemo({ message: messageSent, isResume: false })
// 改为（暂时不支持，需要改 fetchStreamDemo 接受 options）
```

或者改 `getBackoffMs` 函数：

```javascript
function getBackoffMs(attempt) {
  return [100, 500, 2000, 5000, 10000][attempt - 1] || 16000
}
```

## 视频录制脚本（Day 7 后续）

如果要做完整 demo 视频：

1. **录前准备**：
   - 清空 Redis（`docker exec trip-redis redis-cli FLUSHDB`）
   - 终端：clear；浏览器：清空事件日志
2. **脚本**：
   - 0:00 - 0:05 介绍 demo 页面（不录音轨也可以）
   - 0:05 - 0:10 登录
   - 0:10 - 0:15 发送第一条消息，看到流式输出
   - 0:15 - 0:20 点击"模拟断网"，状态栏变化
   - 0:20 - 0:25 自动重连，看到 chunks 继续
   - 0:25 - 0:30 完成，统计展示
   - 0:30 - 0:35 切换到 DevTools Network 标签，展示重连请求的 header
   - 0:35 - end 总结

3. **录屏工具**：
   - macOS：QuickTime Player → 文件 → 新建屏幕录制
   - 或 OBS Studio（更专业）

## 故障排查

| 问题 | 原因 | 解决 |
|---|---|---|
| **登录失败 CORS（Origin null）** | 用 file:// 双击打开，旧 .env 覆盖了 CORS 默认值 | 升级到最新代码：`CORS_ORIGIN` 现在 **merge** 默认值，不再被 .env 覆盖 |
| 登录失败 401 | 密码错 | 确认用 `EvalTest@2026`（首字母大写 E T 0） |
| 发送没反应 | Redis 没起 | `docker ps` 看 trip-redis，没起就 `docker start trip-redis` |
| 续传 404 | streamId 错误或已过期 | 10 分钟 TTL，检查 stream 是否还在 Redis |
| 续传 403 | IDOR — stream 不属于当前用户 | 用同一个 eval-test 账号 |
| chunks 数为 0 | abort 太早，streamId 没下发 | 至少等 3s 再 abort（TTFB ~50ms 后 X-Stream-Id 立即下发） |

## 相关文件

- `trip-server/src/utils/stream.ts` — ResumableStream + resumeStream
- `trip-server/src/services/streamStore.ts` — Redis CRUD
- `trip-server/src/controllers/trip.controller.ts` — 路由分发
- `trip-front/src/api/stream-parser.ts` — SSE 解析 + 退避
- `trip-front/src/api/request.ts` — fetchStream 重连实现
- `trip-front/src/views/Chat.vue` — UI 集成
- `docs/streamable-agent-resumable.md` — 完整设计文档
