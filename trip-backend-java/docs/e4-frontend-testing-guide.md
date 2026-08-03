# E4 前端集成测试指南

## 当前状态

- ✅ Java 后端：`http://localhost:8000`（运行中）
- ⏳ 前端：`http://localhost:5173`（待启动）
- ✅ VITE_API_BASE 已配置：`http://localhost:8000`

## 测试步骤

### 1. 启动前端开发服务器

```bash
cd /Users/wang/Documents/trip/trip-front
npm run dev
```

预期输出：
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
➜  Network: use --host to expose
```

### 2. 浏览器访问验证

打开浏览器访问：`http://localhost:5173`

**预期结果：**
- ✅ 页面正常加载（Trip AI 旅行规划系统）
- ✅ 无 404/500 错误
- ✅ 控制台无 CORS 错误

### 3. API 代理测试

#### 3.1 登录测试

1. 打开浏览器开发者工具（F12）
2. 切换到 **Network** 标签
3. 在登录页面输入：
   - 用户名：`e4test`
   - 密码：`EvalTest@2026`
4. 点击登录

**预期请求：**
```
POST http://localhost:8000/api/user/login
Status: 200 OK
Response: {"code":200,"data":{"token":"...","user":{...}}}
```

#### 3.2 用户信息测试

登录成功后，应自动跳转到首页或对话页面。

**预期请求：**
```
GET http://localhost:8000/api/user/info
Status: 200 OK
Response: {"code":200,"data":{"username":"e4test",...}}
```

#### 3.3 会话列表测试

进入对话页面后，应加载会话列表。

**预期请求：**
```
GET http://localhost:8000/api/conversations
Status: 200 OK
Response: {"code":200,"data":{"items":[],"total":0,...}}
```

#### 3.4 对话测试（核心功能）

发送一条消息："北京2天经典游"

**预期行为：**
1. 立即显示用户消息
2. 开始 SSE 流式响应（打字机效果）
3. 收到响应内容："这是一个模拟的旅行规划响应。E4 测试期间使用简化版本。"
4. 对话保存成功

**网络请求：**
```
POST http://localhost:8000/api/trip/chat
Status: 200 OK
Content-Type: text/event-stream

data: {"type":"chunk","content":"这是一个模拟的旅行规划响应。..."}
data: {"type":"complete","usage":{"prompt":0,...}}
data: {"type":"end"}
```

### 4. 功能检查清单

#### 4.1 登录/注册页面
- [ ] 注册新用户功能正常
- [ ] 登录功能正常
- [ ] 错误提示正确（密码错误、用户不存在）

#### 4.2 首页/对话页面
- [ ] 页面正常加载
- [ ] 显示会话列表（左侧边栏）
- [ ] 可以创建新对话
- [ ] 发送消息功能正常
- [ ] SSE 流式响应显示正常

#### 4.3 用户信息页面
- [ ] 显示当前用户信息
- [ ] 可以修改昵称/头像/简介

#### 4.4 错误处理
- [ ] 401 未认证跳转到登录页
- [ ] 网络错误提示友好
- [ ] 后端 500 错误显示错误提示

### 5. 性能验证

#### 5.1 登录响应时间
- 预期：< 500ms

#### 5.2 SSE 首字时间
- 预期：< 100ms（因为返回固定响应）

#### 5.3 页面加载时间
- 预期：< 2s

### 6. 控制台检查

打开浏览器控制台（F12 → Console）：

**预期：**
- ✅ 无红色错误
- ✅ 无 CORS 错误
- ✅ 无 404 API 请求
- ✅ x-request-id 请求头存在

### 7. 已知差异（可接受）

1. **403 vs 401**
   - 已修复：未认证返回 401（与 Python 一致）

2. **Chat SSE 简化版**
   - 当前返回固定模拟响应
   - 待 D8 接入真实 SseWriter + AgentEngine

3. **Conversations 列表**
   - 当前返回空列表（因为 e4test 用户无历史会话）
   - 功能正常，仅数据为空

## 自动化测试脚本

等 Bash 恢复后运行：

```bash
cd /Users/wang/Documents/trip/trip-backend-java
bash test-e4-frontend.sh
```

## 下一步

如果所有测试通过：
1. 提交前端 .env 配置
2. 继续验证剩余功能（修改行程、反馈等）
3. 运行完整 E4 回归测试

如果测试失败：
1. 记录具体错误信息
2. 检查网络请求（Network tab）
3. 检查控制台错误（Console tab）
4. 对比 Java 后端日志
